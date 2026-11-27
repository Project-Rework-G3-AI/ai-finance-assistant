"""SC-02: kelengkapan field wajib pada hasil ekstraksi.

Yang dijaga test ini adalah aturan penilaian, bukan angka hasilnya. Angka
hasilnya bergerak antar-run karena model bersifat probabilistik, sedangkan
aturannya harus tetap.

SC-02 mengukur **kelengkapan**, bukan kebenaran isi. Test di bawah mengunci
pemisahan itu: nilai yang salah tetapi terbaca tetap dihitung lengkap.

Jebakan yang paling mudah lolos tanpa test: `main.extract` mengisi nilai bawaan
saat model gagal membaca (tanggal hari ini, arah "keluar", bank default). Kalau
kelengkapan diukur dengan "field kosong atau tidak", hasilnya akan tampak
hampir sempurna padahal model tidak membaca apa pun.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sc02_completeness import (  # noqa: E402
    REQUIRED_FIELDS,
    compute,
    score_row,
)

TARGET_SC02 = 0.90

RECORD = {
    "date": "2026-01-01",
    "amount": 800353,
    "bank": "BNI",
    "direction": "keluar",
    "category": "Transfer Antar Bank",
    "note": "",
    "remark": "Ekstraksi AI — wajib ditinjau sebelum dipakai.",
    "mode": "vision",
}

# Acuan hanya dipakai untuk membuktikan bahwa SC-02 **tidak** memakainya.
REFERENCE = {
    "date": "2026-01-01",
    "amount": "800353",
    "bank": "BNI",
    "direction": "keluar",
    "category": "Transfer Antar Bank",
}


# ------------------------------------------------------------ aturan penilaian

def test_complete_row_is_counted_as_complete():
    s = score_row(RECORD)
    assert s["complete"] == "ya"
    assert all(s["readable"].values())


def test_unreadable_field_is_not_rescued_by_the_default_value():
    """Nilai bawaan `main.py` tidak boleh dihitung sebagai terbaca.

    Ini inti SC-02: tanpa aturan ini, hasil akan selalu mendekati 100%.
    """
    rec = dict(RECORD, amount=None,
               remark="Ekstraksi AI — wajib ditinjau. "
                      "(nominal tidak terbaca — isi manual)")
    s = score_row(rec)
    assert s["readable"]["amount"] is False
    assert s["complete"] == "tidak"
    assert s["fallback"]["amount"] is True


def test_date_filled_with_today_still_counts_as_unreadable():
    """`main.py` mengganti tanggal kosong dengan hari ini.

    Nilainya terisi, tetapi bukan hasil membaca gambar — jadi harus dihitung
    gagal, bukan berhasil.
    """
    rec = dict(RECORD, date="2026-11-24",
               remark="Ekstraksi AI — wajib ditinjau. "
                      "(tanggal tidak terbaca — pakai hari ini)")
    s = score_row(rec)
    assert s["readable"]["date"] is False


def test_mock_mode_reads_nothing():
    """Mode mock berarti model tidak dipanggil atau gagal total."""
    s = score_row(dict(RECORD, mode="mock"))
    assert s["complete"] == "tidak"
    assert not any(s["readable"].values())


def test_all_required_fields_are_covered():
    """Kelima field wajib harus benar-benar dinilai, bukan sebagian."""
    s = score_row(RECORD)
    assert set(s["readable"]) == set(REQUIRED_FIELDS)
    assert len(REQUIRED_FIELDS) == 5


# ------------------------------------------------- SC-02 tidak menilai kebenaran

def test_wrong_but_present_value_is_still_complete():
    """Inti pemisahan SC-02 dari SC-01.

    Kategori yang salah tetap dihitung terbaca: SC-02 mengukur kelengkapan,
    bukan kebenaran. Kalau test ini gagal, SC-02 sudah mencampuri urusan SC-01.
    """
    rec = dict(RECORD, category="Kategori Yang Salah Sekali",
               amount=999999999, date="1999-12-31")
    s = score_row(rec)
    assert s["complete"] == "ya"
    assert all(s["readable"].values())


def test_reference_is_ignored_even_when_provided():
    """Acuan tidak boleh mengubah hasil SC-02 sedikit pun.

    `compute` masih menerima `reference` agar pemanggil lama tidak perlu diubah,
    tetapi nilainya harus diabaikan. Kalau acuan ikut dinilai, SC-02 kembali
    menjadi pengukur akurasi.
    """
    rec = dict(RECORD, category="Ngawur",
               remark="Ekstraksi AI — wajib ditinjau.")
    rows = [{"file": "a", "record": rec, "reference": REFERENCE}]
    with_ref = compute(rows)

    rows_without = [{"file": "a", "record": rec}]
    without_ref = compute(rows_without)

    assert with_ref.overall_completeness == without_ref.overall_completeness
    assert with_ref.fields["category"].completeness == pytest.approx(1.0)


def test_score_row_has_no_accuracy_output():
    """Tidak boleh ada sisa keluaran akurasi di hasil penilaian."""
    s = score_row(RECORD)
    assert "correct" not in s
    assert "reference_available" not in s


# -------------------------------------------------------------------- agregat

def test_overall_completeness_averages_per_field_not_per_row():
    """Satu field yang selalu gagal tidak boleh tertutup empat field yang baik."""
    pocket_failures = "Ekstraksi AI — wajib ditinjau. (kantong tidak terbaca — pakai default)"
    rows = [
        {"file": "a", "record": dict(RECORD, remark=pocket_failures)},
        {"file": "b", "record": dict(RECORD, remark=pocket_failures)},
    ]
    c = compute(rows)
    assert c.fields["date"].completeness == pytest.approx(1.0)
    assert c.fields["bank"].completeness == pytest.approx(0.0)
    assert c.overall_completeness == pytest.approx((1.0 * 4 + 0.0) / 5)

    rows2 = [
        {"file": "a", "record": dict(RECORD, remark=pocket_failures)},
        {"file": "b", "record": RECORD},
    ]
    c2 = compute(rows2)
    assert c2.fields["bank"].completeness == pytest.approx(0.5)
    assert c2.overall_completeness == pytest.approx((1.0 * 4 + 0.5) / 5)


def test_all_fields_complete_counts_only_fully_readable_rows():
    rows = [
        {"file": "a", "record": RECORD},
        {"file": "b", "record": dict(RECORD, mode="mock")},
    ]
    c = compute(rows)
    assert c.all_fields_complete == 1


def test_empty_input_is_rejected():
    with pytest.raises(ValueError):
        compute([])


def test_target_constant_matches_the_brd():
    """Target BRD: minimal 90% field wajib terisi."""
    assert TARGET_SC02 == pytest.approx(0.90)
