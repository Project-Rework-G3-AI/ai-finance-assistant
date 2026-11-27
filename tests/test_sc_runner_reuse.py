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

ROW_VISION = {
    "file": "a",
    "record": {"date": "2026-01-01", "amount": 1000, "bank": "BNI",
               "direction": "keluar", "category": "Bahan Baku",
               "remark": "", "mode": "vision"},
    "reference": {"date": "2026-01-01", "amount": "1000", "bank": "BNI",
                  "direction": "", "category": "Bahan Baku"},
}


def test_report_names_the_number_used_to_judge_the_target(tmp_path):
    """Laporan wajib menyebut angka mana yang dibandingkan dengan target.

    Tanpa ini, pembaca melihat beberapa persentase lalu menebak sendiri mana
    yang dipakai. Status "BELUM TERCAPAI" saja tidak cukup, karena tidak
    menjelaskan dari kolom mana angka itu diambil.
    """
    import sc_runner

    text = sc_runner.write_sc02_report([ROW_VISION], tmp_path)["text"]
    assert "Angka yang dinilai" in text
    assert "kelengkapan rata-rata" in text
    assert "dibandingkan dengan target" in text
    assert "Status" in text


def test_report_states_how_many_fields_are_averaged(tmp_path):
    """Penyebut harus disebut: kelima field wajib, bukan sebagian."""
    import sc_runner

    text = sc_runner.write_sc02_report([ROW_VISION], tmp_path)["text"]
    assert "5 field" in text


def test_wrong_values_do_not_change_the_judged_number(tmp_path):
    """Nilai salah tidak boleh menurunkan SC-02.

    SC-02 mengukur kelengkapan. Kategori WRONG tetap terbaca, jadi angkanya
    harus sama dengan baris yang nilainya benar.
    """
    import sc_runner

    (tmp_path / "a").mkdir(parents=True, exist_ok=True)
    benar = sc_runner.write_sc02_report([ROW_VISION], tmp_path / "a")["text"]
    (tmp_path / "b").mkdir(parents=True, exist_ok=True)
    salah_row = dict(ROW_VISION,
                     record=dict(ROW_VISION["record"], category="WRONG"))
    salah = sc_runner.write_sc02_report([salah_row], tmp_path / "b")["text"]

    def angka(t):
        baris = [x for x in t.splitlines() if x.startswith("Angka yang dinilai")]
        return baris[0]

    assert angka(benar) == angka(salah)


def test_compute_ignores_reference_entirely():
    """Acuan tidak boleh mengubah hasil, walau pemanggil masih mengirimnya."""
    from sc02_completeness import compute

    salah = {"file": "a", "record": dict(ROW_VISION["record"], category="WRONG")}
    c_tanpa = compute([salah])
    c_dengan = compute([dict(salah, reference=ROW_VISION["reference"])])
    assert c_tanpa.overall_completeness == c_dengan.overall_completeness


def test_unreadable_field_still_lowers_the_judged_number(tmp_path):
    """Kebalikannya: field yang tidak terbaca harus benar-benar menurunkan."""
    import sc_runner

    gagal = dict(ROW_VISION,
                 record=dict(ROW_VISION["record"], remark="(kantong tidak terbaca — pakai default)"))
    text = sc_runner.write_sc02_report([gagal], tmp_path)["text"]
    assert "BELUM TERCAPAI" in text


def test_metrics_json_has_no_accuracy_keys(tmp_path):
    """Berkas metrik tidak boleh lagi memuat sisa medan akurasi."""
    import json

    import sc_runner

    sc_runner.write_sc02_report([ROW_VISION], tmp_path)
    data = json.loads((tmp_path / "sc02_metrics.json").read_text(encoding="utf-8"))
    assert "overall_accuracy" not in data
    for isi in data["fields"].values():
        assert "accuracy" not in isi
        assert "correct" not in isi
        assert "scored" not in isi


def test_restart_truncates_the_old_results_file(tmp_path, monkeypatch):
    """`--restart` harus memotong berkas hasil lama, bukan menambahinya.

    Berkas hasil ditulis dalam mode "a" supaya hasil yang sudah ada tidak hilang
    saat proses mati di tengah. Tanpa pemotongan, `--restart` menambahkan hasil
    baru di atas hasil lama dan satu gambar punya dua baris. Ini pernah terjadi:
    65 gambar menjadi 70 baris.
    """
    import asyncio

    import sc_common as cfg
    import sc_runner

    out = tmp_path / "results_per_row.csv"
    # Berkas lama dengan satu baris hasil usang.
    out.write_text(
        ",".join(sc_runner.OUTPUT_COLUMNS) + "\n"
        + "gambar-lama.jpg,,,,,,,,,,,,,,,\n",
        encoding="utf-8")
    assert len(out.read_text(encoding="utf-8").strip().splitlines()) == 2

    pairs = [{"file": "gambar-baru.jpg"}]
    images = tmp_path / "img"
    images.mkdir()
    (images / "gambar-baru.jpg").write_bytes(b"\xff\xd8\xff")

    async def fake_extract(client, name, image_bytes, caption):
        return {"tanggal": "2026-01-01", "nominal": 1000, "bank": "BNI",
                "arah": "keluar", "kategori": "X", "keterangan": "uji",
                "catatan": "", "mode": "vision"}

    import main

    # Test ini tidak boleh butuh kunci model: yang diuji pemotongan berkas,
    # bukan pemanggilan AI. `run_pairs` menolak jalan tanpa kunci, jadi kunci
    # tiruan dipasang supaya test tetap gratis.
    monkeypatch.setattr(main, "AI_KEY", "test-key-not-used")

    asli_extract = main.extract
    main.extract = fake_extract
    try:
        asyncio.run(sc_runner.run_pairs(pairs, images, out, restart=True))
    finally:
        main.extract = asli_extract

    isi = out.read_text(encoding="utf-8").strip().splitlines()
    berkas = [b.split(",")[0] for b in isi[1:]]
    assert "gambar-lama.jpg" not in berkas, (
        "hasil lama masih ada setelah --restart; berkas tidak dipotong")
    assert berkas == ["gambar-baru.jpg"], f"baris hasil tidak seperti diharapkan: {berkas}"

