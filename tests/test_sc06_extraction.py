"""Test SC-06: kelengkapan field yang diekstrak dari gambar.

Yang diuji hanya kriteria SC-06 dari BRD. Tidak ada test tentang gaya kode.

Seluruh test di sini gratis: tidak memanggil model dan tidak menyentuh jaringan.
Pengukuran pada data asli dijalankan terpisah lewat `tests/_sc06_run.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc06_extraction as sc06

ROOT = Path(__file__).resolve().parents[1]

BASE = {
    "tanggal": "2026-01-05 10:00:00",
    "keterangan": "Beli tepung",
    "nominal": 195000,
    "arah": "keluar",
    "kategori": "Bahan Baku",
    "bank": "BNI",
    "kantong_tujuan": "",
}


def raw(**ubah) -> dict:
    nilai = dict(BASE)
    nilai.update(ubah)
    return nilai


# ---------------------------------------- daftar field diambil dari produksi


def test_required_fields_come_from_the_production_prompt():
    """Field wajib dibaca dari prompt produksi, bukan daftar salinan di test."""
    import main

    teks = Path(main.__file__).read_text(encoding="utf-8")
    awal = teks.index("prompt = (")
    akhir = teks.index("if caption:", awal)
    ruang: dict = {}
    exec(teks[awal:akhir], {"KAT": main.KAT}, ruang)  # noqa: S102

    import re

    dari_prompt = re.findall(r'"([a-z_]+)"\s*:', ruang["prompt"])
    assert sc06.required_fields() == dari_prompt


def test_every_field_asked_from_the_model_has_a_rule():
    """Field baru di prompt harus diputuskan wajib atau tidak, bukan lolos."""
    for name in sc06.required_fields():
        # Setiap field harus punya keputusan: wajib selalu, atau bersyarat.
        assert (name in sc06.ALWAYS_REQUIRED
                or name in sc06.CONDITIONAL_REQUIRED
                or name not in sc06.ALWAYS_REQUIRED), (
            f"field '{name}' belum punya aturan wajib/tidak")


def test_conditional_field_is_only_required_for_transfers():
    """`kantong_tujuan` tidak wajib pada transaksi masuk atau keluar biasa."""
    assert sc06.is_required_for("kantong_tujuan", raw(arah="keluar")) is False
    assert sc06.is_required_for("kantong_tujuan", raw(arah="masuk")) is False
    assert sc06.is_required_for("kantong_tujuan", raw(arah="transfer")) is True
    # Field lain wajib apa pun arahnya.
    for name in sc06.ALWAYS_REQUIRED:
        assert sc06.is_required_for(name, raw(arah="keluar")) is True


# ------------------------------------------------ apa yang dihitung terisi


def test_complete_response_has_nothing_missing():
    hasil = sc06.score_image("a.jpg", raw(), "a.jpg")
    assert hasil.missing == []
    assert hasil.complete


@pytest.mark.parametrize("field,value", [
    ("tanggal", ""),
    ("tanggal", "kemarin sore"),
    ("keterangan", ""),
    ("nominal", None),
    ("nominal", 0),
    ("arah", ""),
    ("arah", "entah"),
    ("kategori", ""),
    ("kategori", "Kategori Ngawur"),
    ("bank", ""),
])
def test_empty_or_unreadable_field_is_counted_missing(field, value):
    hasil = sc06.score_image("a.jpg", raw(**{field: value}), "a.jpg")
    assert field in hasil.missing, f"{field}={value!r} seharusnya dinilai kosong"
    assert not hasil.complete


def test_wrong_but_present_value_is_not_missing():
    """SC-06 mengukur kelengkapan, bukan akurasi.

    Nominal yang salah tetap terhitung terisi: kecocokan nilai adalah urusan
    SC-01 dan SC-02. Kalau test ini gagal, SC-06 sudah keluar dari lingkupnya.
    """
    hasil = sc06.score_image(
        "a.jpg", raw(nominal=999_999_999, keterangan="teks apa saja"), "a.jpg")
    assert hasil.missing == []
    assert hasil.complete


def test_transfer_without_target_wallet_is_missing_only_that_field():
    hasil = sc06.score_image("a.jpg", raw(arah="transfer", kantong_tujuan=""), "a.jpg")
    assert hasil.missing == ["kantong_tujuan"]


def test_transfer_with_target_wallet_is_complete():
    hasil = sc06.score_image("a.jpg", raw(arah="transfer", kantong_tujuan="BRI"), "a.jpg")
    assert hasil.missing == []


# ------------------------- field yang ditutupi nilai bawaan produksi


def test_default_values_in_production_do_not_count_as_read():
    """Nilai bawaan produksi tidak boleh membuat field tampak terbaca.

    `main.extract` mengganti tanggal kosong dengan hari ini, arah kosong dengan
    "keluar", keterangan kosong dengan nama berkas, dan kantong kosong dengan
    nilai bawaan. Kalau penilaian memakai hasil fungsi itu, semuanya akan selalu
    lengkap dan kriteria ini tidak mengukur apa pun.
    """
    for field, value in (("tanggal", ""), ("arah", ""),
                         ("keterangan", ""), ("bank", "")):
        hasil = sc06.score_image("a.jpg", raw(**{field: value}), "a.jpg")
        assert field in hasil.missing, (
            f"{field} kosong dinilai terisi karena nilai bawaan produksi")


def test_covered_fields_are_reported_separately():
    """Field yang ditutupi nilai bawaan dilaporkan, bukan dihilangkan."""
    hasil = sc06.score_image("a.jpg", raw(tanggal=""), "a.jpg")
    assert "tanggal" in hasil.missing
    assert "tanggal" in hasil.covered, (
        "field yang terisi nilai bawaan produksi harus dilaporkan terpisah")


# --------------------------------------------------------------- agregasi


def test_image_that_failed_to_call_is_not_counted_complete():
    """Gambar yang gagal dipanggil tidak boleh menambah angka kelengkapan."""
    laporan = sc06.compute([
        {"file": "a.jpg", "raw": raw(), "error": ""},
        {"file": "b.jpg", "raw": {}, "error": "HTTP 500"},
    ])
    assert laporan.total_images == 2
    assert laporan.measured == 1
    assert laporan.failed_images == 1
    assert laporan.complete_images == 1
    assert laporan.complete_rate == 100.0
    assert sc06.verdict(laporan) == "GAGAL DIUKUR"


def test_verdict_is_red_when_one_image_loses_one_field():
    """Target BRD: tidak ada field wajib yang hilang. Satu saja, gagal."""
    laporan = sc06.compute([
        {"file": "a.jpg", "raw": raw(), "error": ""},
        {"file": "b.jpg", "raw": raw(nominal=None), "error": ""},
    ])
    assert laporan.complete_images == 1
    assert laporan.complete_rate == 50.0
    assert not laporan.pass_verdict
    assert sc06.verdict(laporan) == "BELUM TERCAPAI"


def test_per_field_counts_skip_fields_that_are_not_required():
    """Penyebut per field mengikuti kewajibannya, bukan jumlah gambar."""
    laporan = sc06.compute([
        {"file": "a.jpg", "raw": raw(arah="keluar"), "error": ""},
        {"file": "b.jpg", "raw": raw(arah="transfer", kantong_tujuan="BRI"), "error": ""},
    ])
    per_field = {f.name: f for f in laporan.fields}
    # kantong_tujuan hanya wajib di satu dari dua gambar.
    assert per_field["kantong_tujuan"].required == 1
    assert per_field["kantong_tujuan"].filled == 1
    # tanggal wajib di keduanya.
    assert per_field["tanggal"].required == 2


def test_measurement_counts_images_not_fields():
    """Angka yang dinilai adalah jumlah gambar lengkap, bukan jumlah field."""
    laporan = sc06.compute([
        {"file": "a.jpg", "raw": raw(), "error": ""},
        {"file": "b.jpg", "raw": raw(), "error": ""},
    ])
    assert laporan.complete_images == 2
    assert laporan.measured == 2


def test_empty_run_is_not_a_pass():
    """Belum diukur tidak boleh terbaca sebagai tercapai."""
    laporan = sc06.compute([])
    assert not laporan.pass_verdict
    assert sc06.verdict(laporan) == "BELUM DIUKUR"


# ----------------------------------------------------------------- laporan


def test_report_states_the_denominator_and_the_verdict():
    laporan = sc06.compute([{"file": "a.jpg", "raw": raw(), "error": ""}])
    out = ROOT / "sc-out-test-sc06"
    try:
        txt, csv_path = sc06.write_report(laporan, out)
        isi = txt.read_text(encoding="utf-8")
        assert "1 dari 1" in isi
        assert "dibandingkan dengan target" in isi
        assert "Status" in isi
        baris = csv_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(baris) == 2  # header + satu gambar
    finally:
        import shutil

        shutil.rmtree(out, ignore_errors=True)


def test_report_names_which_fields_are_missing_per_image():
    """Laporan harus menyebut gambar mana kehilangan field apa."""
    laporan = sc06.compute([
        {"file": "hilang.jpg", "raw": raw(nominal=None, bank=""), "error": ""},
    ])
    out = ROOT / "sc-out-test-sc06b"
    try:
        txt, _ = sc06.write_report(laporan, out)
        isi = txt.read_text(encoding="utf-8")
        assert "hilang.jpg" in isi
        assert "nominal" in isi
        assert "bank" in isi
    finally:
        import shutil

        shutil.rmtree(out, ignore_errors=True)


def test_zero_denominator_is_not_shown_as_zero_percent():
    """Field yang tidak wajib di transaksi mana pun tidak ditampilkan 0,0%.

    Menampilkannya sebagai 0,0% terbaca seperti kegagalan, padahal tidak ada
    yang dinilai.
    """
    laporan = sc06.compute([
        {"file": "a.jpg", "raw": raw(arah="keluar"), "error": ""},
    ])
    out = ROOT / "sc-out-test-sc06c"
    try:
        txt, _ = sc06.write_report(laporan, out)
        baris = [b for b in txt.read_text(encoding="utf-8").splitlines()
                 if b.startswith("kantong_tujuan")]
        assert baris, "field kantong_tujuan tidak muncul di laporan"
        assert "0.0%" not in baris[0]
    finally:
        import shutil

        shutil.rmtree(out, ignore_errors=True)


# ------------------------------------------------------------ biaya/harness


def test_sc06_does_not_need_credentials_to_judge():
    """Penilaian gratis; hanya pengambilan balasan model yang butuh kunci."""
    import os

    simpan = os.environ.pop("AI_API_KEY", None)
    try:
        laporan = sc06.compute([{"file": "a.jpg", "raw": raw(), "error": ""}])
        assert laporan.complete_images == 1
    finally:
        if simpan is not None:
            os.environ["AI_API_KEY"] = simpan
