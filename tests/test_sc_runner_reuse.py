"""Perilaku saat hasil lama dipakai lagi.

Runner menyimpan hasil per gambar ke CSV dan melanjutkan dari situ, supaya run
yang terputus tidak perlu mengulang gambar yang sudah selesai. Perilaku itu
benar, tetapi berbahaya kalau tidak terlihat: run yang tidak memanggil model
sama sekali selesai dalam sedetik dan langsung mencetak angka, sehingga wajar
disangka modelnya menjadi jauh lebih cepat.

Test ini mengunci tiga hal:

1. Pemakaian hasil lama selalu diumumkan dengan jelas.
2. Angka dari run lama tidak bisa dikutip sebagai hasil hitung baru, karena
   asalnya tercatat di `source.json` dan muncul di kepala laporan.
3. Hasil yang dibuat dengan daftar pasangan berbeda ditolak, bukan dilaporkan
   sebagai angka yang sah.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sc_runner import (  # noqa: E402
    describe_reuse,
    read_source,
    source_line,
    stale_files,
    write_source,
)


# --------------------------------------------------------- pengumuman reuse

def test_reuse_is_announced_loudly_when_nothing_is_left():
    teks = describe_reuse({"a": {}, "b": {}}, [])
    assert "HASIL LAMA DIPAKAI LAGI" in teks
    assert "TIDAK ADA PEMANGGILAN MODEL BARU" in teks
    assert "panggilan model  : 0" in teks


def test_reuse_message_points_at_restart_and_metrics_only():
    teks = describe_reuse({"a": {}}, [])
    assert "--restart" in teks
    assert "--metrics-only" in teks


def test_partial_reuse_reports_the_split():
    """Kalau sebagian sudah ada, jumlahnya harus terbaca, bukan disamarkan."""
    teks = describe_reuse({"a": {}, "b": {}}, [{"file": "c"}])
    assert "sudah ada di CSV : 2 dari 3 gambar" in teks
    assert "akan diproses    : 1 gambar" in teks


def test_partial_reuse_does_not_claim_zero_calls():
    """Saat masih ada sisa, jangan bilang tidak ada panggilan model."""
    teks = describe_reuse({"a": {}}, [{"file": "b"}])
    assert "TIDAK ADA PEMANGGILAN MODEL BARU" not in teks


# ------------------------------------------------------- deteksi hasil basi

def test_stale_files_detects_rows_from_another_pair_set():
    done = {"a.jpg": {}, "b.jpg": {}}
    pairs = [{"file": "a.jpg"}]
    assert stale_files(done, pairs) == ["b.jpg"]


def test_stale_files_is_empty_when_pair_set_matches():
    done = {"a.jpg": {}, "b.jpg": {}}
    pairs = [{"file": "a.jpg"}, {"file": "b.jpg"}]
    assert stale_files(done, pairs) == []


def test_stale_files_ignores_whitespace_differences():
    done = {"a.jpg": {}}
    assert stale_files(done, [{"file": " a.jpg "}]) == []


def test_stale_files_returns_sorted_names_for_a_stable_message():
    done = {"z.jpg": {}, "a.jpg": {}}
    assert stale_files(done, []) == ["a.jpg", "z.jpg"]


# ------------------------------------------------------------ asal angka

def test_source_records_zero_calls_when_results_are_reused(tmp_path):
    write_source(tmp_path, model_calls=0)
    assert read_source(tmp_path)["model_calls"] == 0
    assert "Tidak ada panggilan model" in source_line(tmp_path)


def test_source_line_names_the_model_when_it_was_called(tmp_path):
    write_source(tmp_path, model_calls=65, model="contoh/model",
                 computed_at="2026-01-01 10:00:00 UTC")
    teks = source_line(tmp_path)
    assert "65 panggilan model" in teks
    assert "contoh/model" in teks


def test_source_line_is_honest_when_nothing_was_recorded(tmp_path):
    assert "tidak tercatat" in source_line(tmp_path)


def test_write_source_merges_instead_of_dropping_previous_fields(tmp_path):
    """Menjalankan ulang tidak boleh menghapus keterangan yang sudah ada."""
    write_source(tmp_path, computed_at="2026-01-01", model="a/b")
    write_source(tmp_path, model_calls=0)
    data = read_source(tmp_path)
    assert data["computed_at"] == "2026-01-01"
    assert data["model"] == "a/b"
    assert data["model_calls"] == 0


def test_source_json_is_written_inside_the_output_directory(tmp_path):
    write_source(tmp_path, model_calls=1)
    assert (tmp_path / "source.json").exists()
