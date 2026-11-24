"""SC-02: kelengkapan field wajib pada hasil ekstraksi.

Yang dijaga test ini adalah aturan penilaian, bukan angka hasilnya. Angka
hasilnya bergerak antar-run karena model bersifat probabilistik, sedangkan
aturannya harus tetap.

Jebakan yang paling mudah lolos tanpa test: `main.extract` mengisi nilai bawaan
saat model gagal membaca (tanggal hari ini, arah "keluar", bank default). Kalau
kelengkapan diukur dengan "field kosong atau tidak", hasilnya akan tampak
hampir sempurna padahal model tidak membaca apa pun. Test di bawah mengunci
perilaku yang benar.
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

REFERENCE = {
    "date": "2026-01-01",
    "amount": "800353",
    "bank": "BNI",
    "direction": "keluar",
    "category": "Transfer Antar Bank",
}


# ------------------------------------------------------------ aturan penilaian

def test_complete_row_is_counted_as_complete():
    s = score_row(RECORD, REFERENCE)
    assert s["complete"] == "ya"
    assert all(s["readable"].values())
    assert all(s["correct"].values())


def test_unreadable_field_is_not_rescued_by_the_default_value():
    """Nilai bawaan `main.py` tidak boleh dihitung sebagai terbaca.

    Ini inti SC-02: tanpa aturan ini, hasil akan selalu mendekati 100%.
    """
    rec = dict(RECORD, amount=None,
               remark="Ekstraksi AI — wajib ditinjau. "
                      "(nominal tidak terbaca — isi manual)")
    s = score_row(rec, REFERENCE)
    assert s["readable"]["amount"] is False
    assert s["correct"]["amount"] is False
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
    s = score_row(rec, REFERENCE)
    assert s["readable"]["date"] is False
    assert s["correct"]["date"] is False


def test_mock_mode_reads_nothing():
    """Mode mock berarti model tidak dipanggil atau gagal total."""
    s = score_row(dict(RECORD, mode="mock"), REFERENCE)
    assert s["complete"] == "tidak"
    assert not any(s["readable"].values())


def test_amount_is_compared_numerically_not_textually():
    """Model bisa membalas 800353 sementara acuan menyimpan 800353.0."""
    s = score_row(dict(RECORD, amount="800353.0"), REFERENCE)
    assert s["correct"]["amount"] is True


def test_date_format_differences_are_normalized():
    s = score_row(dict(RECORD, date="01/01/2026"), REFERENCE)
    assert s["correct"]["date"] is True


def test_without_reference_only_readability_is_judged():
    """Untuk 118 gambar tanpa acuan, hanya keterbacaan yang bisa dinilai."""
    s = score_row(RECORD, None)
    assert s["reference_available"] == "tidak"
    assert s["complete"] == "ya"
    assert not any(s["correct"].values())


def test_all_required_fields_are_covered():
    """Kelima field wajib harus benar-benar dinilai, bukan sebagian."""
    s = score_row(RECORD, REFERENCE)
    assert set(s["readable"]) == set(REQUIRED_FIELDS)
    assert len(REQUIRED_FIELDS) == 5


# -------------------------------------------------------------------- agregat

def test_overall_completeness_averages_per_field_not_per_row():
    """Satu field yang selalu gagal tidak boleh tertutup empat field yang baik."""
    # Kantong sengaja dibuat gagal di kedua baris, field lain berhasil.
    gagal_kantong = "Ekstraksi AI — wajib ditinjau. (kantong tidak terbaca — pakai default)"
    rows = [
        {"file": "a", "record": dict(RECORD, remark=gagal_kantong),
         "reference": REFERENCE},
        {"file": "b", "record": dict(RECORD, remark=gagal_kantong),
         "reference": REFERENCE},
    ]
    c = compute(rows)
    # tanggal, nominal, arah, kategori terbaca 2/2; kantong 0/2
    assert c.fields["date"].completeness == pytest.approx(1.0)
    assert c.fields["bank"].completeness == pytest.approx(0.0)
    assert c.overall_completeness == pytest.approx((1.0 * 4 + 0.0) / 5)
    # Rata-rata per baris akan memberi 0.8, per field memberi angka yang sama
    # di sini — jadi diuji dengan satu field gagal di separuh baris.
    rows2 = [
        {"file": "a", "record": dict(RECORD, remark=gagal_kantong),
         "reference": REFERENCE},
        {"file": "b", "record": RECORD, "reference": REFERENCE},
    ]
    c2 = compute(rows2)
    assert c2.fields["bank"].completeness == pytest.approx(0.5)
    assert c2.overall_completeness == pytest.approx((1.0 * 4 + 0.5) / 5)


def test_all_fields_complete_counts_only_fully_readable_rows():
    rows = [
        {"file": "a", "record": RECORD, "reference": REFERENCE},
        {"file": "b", "record": dict(RECORD, mode="mock"), "reference": REFERENCE},
    ]
    c = compute(rows)
    assert c.all_fields_complete == 1


def test_empty_input_is_rejected():
    with pytest.raises(ValueError):
        compute([])


def test_target_constant_matches_the_brd():
    """Target BRD: minimal 90% field wajib terbaca benar."""
    assert TARGET_SC02 == pytest.approx(0.90)
