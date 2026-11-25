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
    text = describe_reuse({"a": {}, "b": {}}, [])
    assert "HASIL LAMA DIPAKAI LAGI" in text
    assert "TIDAK ADA PEMANGGILAN MODEL BARU" in text
    assert "panggilan model  : 0" in text


def test_reuse_message_points_at_restart_and_metrics_only():
    text = describe_reuse({"a": {}}, [])
    assert "--restart" in text
    assert "--metrics-only" in text


def test_partial_reuse_reports_the_split():
    """Kalau sebagian sudah ada, jumlahnya harus terbaca, bukan disamarkan."""
    text = describe_reuse({"a": {}, "b": {}}, [{"file": "c"}])
    assert "sudah ada di CSV : 2 dari 3 gambar" in text
    assert "akan diproses    : 1 gambar" in text


def test_partial_reuse_does_not_claim_zero_calls():
    """Saat masih ada sisa, jangan bilang tidak ada panggilan model."""
    text = describe_reuse({"a": {}}, [{"file": "b"}])
    assert "TIDAK ADA PEMANGGILAN MODEL BARU" not in text


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
    write_source(tmp_path, model_calls=65, model="example/model",
                 computed_at="2026-01-01 10:00:00 UTC")
    text = source_line(tmp_path)
    assert "65 panggilan model" in text
    assert "example/model" in text


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


# ------------------------------------------- angka yang dipakai menilai target

def test_report_names_the_number_used_to_judge_the_target(tmp_path):
    """Laporan wajib menyebut angka mana yang dibandingkan dengan target.

    Tanpa ini, pembaca melihat kelengkapan 98,2% dan kecocokan 72,5% lalu
    menebak sendiri mana yang dipakai. Status "BELUM TERCAPAI" saja tidak
    cukup, karena tidak menjelaskan dari kolom mana angka itu diambil.
    """
    import sc_runner

    rows = [
        {"file": "a", "record": {"date": "2026-01-01", "amount": 1000,
                                 "bank": "BNI", "direction": "keluar",
                                 "category": "Bahan Baku", "remark": "", "mode": "vision"},
         "reference": {"date": "2026-01-01", "amount": "1000",
                       "bank": "BNI", "direction": "", "category": "Bahan Baku"}},
    ]
    rep = sc_runner.write_sc02_report(rows, tmp_path)
    text = rep["text"]

    assert "Angka yang dinilai" in text
    assert "kecocokan rata-rata" in text
    assert "dibandingkan dengan target" in text
    assert "Status" in text


def test_report_states_the_denominator_of_the_average(tmp_path):
    """Penyebut harus disebut: 4 field beracuan, bukan 5."""
    import sc_runner

    rows = [
        {"file": "a", "record": {"date": "2026-01-01", "amount": 1000,
                                 "bank": "BNI", "direction": "keluar",
                                 "category": "Bahan Baku", "remark": "", "mode": "vision"},
         "reference": {"date": "2026-01-01", "amount": "1000",
                       "bank": "BNI", "direction": "", "category": "Bahan Baku"}},
    ]
    text = sc_runner.write_sc02_report(rows, tmp_path)["text"]
    assert "4 field beracuan" in text


def test_report_shows_accuracy_without_category(tmp_path):
    """Sebab kegagalan harus terbaca, bukan tersembunyi di rata-rata."""
    import sc_runner

    rows = [
        {"file": "a", "record": {"date": "2026-01-01", "amount": 1000,
                                 "bank": "BNI", "direction": "keluar",
                                 "category": "WRONG", "remark": "", "mode": "vision"},
         "reference": {"date": "2026-01-01", "amount": "1000",
                       "bank": "BNI", "direction": "", "category": "Bahan Baku"}},
    ]
    text = sc_runner.write_sc02_report(rows, tmp_path)["text"]
    assert "kecocokan tanpa kategori" in text


def test_scored_count_counts_only_fields_with_a_reference():
    from sc02_completeness import compute

    rows = [
        {"file": "a", "record": {"date": "2026-01-01", "amount": 1000,
                                 "bank": "BNI", "direction": "keluar",
                                 "category": "Bahan Baku", "remark": "", "mode": "vision"},
         "reference": {"date": "2026-01-01", "amount": "1000",
                       "bank": "BNI", "direction": "", "category": "Bahan Baku"}},
    ]
    c = compute(rows)
    assert c.scored_count == 4  # direction tanpa acuan tidak ikut


def test_accuracy_excluding_removes_only_the_named_field():
    from sc02_completeness import compute

    rows = [
        {"file": "a", "record": {"date": "2026-01-01", "amount": 1000,
                                 "bank": "BNI", "direction": "keluar",
                                 "category": "WRONG", "remark": "", "mode": "vision"},
         "reference": {"date": "2026-01-01", "amount": "1000",
                       "bank": "BNI", "direction": "", "category": "Bahan Baku"}},
    ]
    c = compute(rows)
    without = c.accuracy_excluding("category")
    assert without > c.overall_accuracy
    assert without == pytest.approx(1.0)


def test_accuracy_excluding_returns_zero_when_nothing_left():
    from sc02_completeness import compute

    rows = [
        {"file": "a", "record": {"date": "2026-01-01", "amount": 1000,
                                 "bank": "BNI", "direction": "keluar",
                                 "category": "Bahan Baku", "remark": "", "mode": "vision"},
         "reference": {"date": "2026-01-01", "amount": "1000",
                       "bank": "BNI", "direction": "", "category": "Bahan Baku"}},
    ]
    c = compute(rows)
    assert c.accuracy_excluding("date", "amount", "bank", "category") == 0.0
