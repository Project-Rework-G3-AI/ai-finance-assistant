"""Penjaga untuk angka jumlah baris pada tanya jawab.

Latar belakang: SC-08 pernah gagal karena model melaporkan "15 baris" sebagai
jumlah seluruh transaksi. Penyebabnya bukan model, melainkan tidak adanya cara
menanyakan jumlah baris: `list_rows` memotong hasilnya tanpa memberi tahu, dan
tidak ada tool yang melaporkan jumlah sebenarnya. Model lalu menghitung panjang
daftar yang sudah terpotong.

Test di sini mengunci perbaikannya: jumlah baris tersedia sebagai angka pasti,
tidak ikut berubah karena penyaring arah, dan tetap benar walau daftar barisnya
dipotong.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _sc08_reference as reference  # noqa: E402
from cash_report import qa  # noqa: E402

AWAL = date(2026, 1, 1)
AKHIR = date(2026, 2, 1)


def rows_of(count: int, kategori: str = "Bahan Baku", status: str = "verified") -> list[list]:
    """`count` baris keluar pada Januari 2026, satu per hari."""
    return [
        [
            f"2026-01-{(i % 28) + 1:02d} 09:00:00", "BNI", "", 1000,
            kategori, f"baris {i}", status, "", f"r{i}", f"f{i}.jpg", "",
        ]
        for i in range(count)
    ]


# ------------------------------------------------------ jumlah baris tersedia

def test_count_rows_counts_every_row_without_truncating():
    """71 baris harus dilaporkan 71, bukan 50 atau 15."""
    rows = rows_of(71)
    assert qa.count_rows(rows, AWAL, AKHIR) == 71


def test_count_rows_is_not_capped_like_list_rows():
    """Batas 50 pada list_rows tidak boleh ikut membatasi jumlah baris."""
    rows = rows_of(60)
    listed = qa.list_rows(rows, AWAL, AKHIR, limit=100)
    assert len(listed) == 50, "list_rows memang dipotong di 50; itu bukan bug, tapi batasnya"
    assert qa.count_rows(rows, AWAL, AKHIR) == 60, (
        "jumlah baris tidak boleh ikut terpotong"
    )


def test_aggregate_reports_the_row_count():
    """Angka jumlah baris harus tersedia juga lewat aggregate."""
    rows = rows_of(71)
    assert qa.aggregate(rows, AWAL, AKHIR)["jumlah_baris"] == 71


def test_row_count_does_not_change_with_direction():
    """Satu transaksi tetap satu baris, ditanya dari arah mana pun."""
    rows = rows_of(10) + [
        ["2026-01-15 09:00:00", "BNI", 5000, "", "Penjualan Produk", "masuk", "verified", "", "m1", "g.jpg", ""],
    ]
    semua = qa.count_rows(rows, AWAL, AKHIR)
    masuk = qa.count_rows(rows, AWAL, AKHIR, arah="masuk")
    keluar = qa.count_rows(rows, AWAL, AKHIR, arah="keluar")

    assert semua == 11
    assert (masuk, keluar) == (1, 10)
    assert masuk + keluar == semua, "penyaringan arah tidak boleh menghilangkan baris"

    # Dan lewat aggregate, jumlah baris tetap 11 walau arah disebut.
    assert qa.aggregate(rows, AWAL, AKHIR, arah="masuk")["jumlah_baris"] == 11
    assert qa.aggregate(rows, AWAL, AKHIR, arah="keluar")["jumlah_baris"] == 11


def test_row_count_includes_transfers():
    """Transfer memang di luar total uang, tapi tetap satu baris tercatat."""
    rows = rows_of(3) + [
        ["2026-01-10 09:00:00", "BNI", "", 7000, "Transfer Antar Bank", "pindah", "verified", "", "t1", "h.jpg", ""],
        ["2026-01-10 09:00:00", "BRI", 7000, "", "Transfer Antar Bank", "pindah", "verified", "", "t1", "h.jpg", ""],
    ]
    tot = qa.aggregate(rows, AWAL, AKHIR)
    assert tot["jumlah_baris"] == 5, "dua baris transfer tetap dihitung sebagai baris"
    assert tot["verified"]["n"] == 3, "tapi transfer tetap di luar jumlah baris verified"


def test_rows_without_an_amount_are_still_counted():
    """Baris tanpa nominal tetap satu baris tercatat, jadi tetap dihitung.

    Ini kasus nyata: satu baris hasil ekstraksi nominalnya kosong dan tetap
    ditulis ke sheet dengan catatan. Menghitungnya sebagai nol baris akan
    membuat jumlah transaksi lebih kecil dari isi sheet.
    """
    rows = rows_of(3) + [
        ["2026-01-20 09:00:00", "BNI", "", "", "Bahan Baku", "nominal kosong", "draft", "perlu dilengkapi", "z1", "z.jpg", ""],
    ]
    assert qa.count_rows(rows, AWAL, AKHIR) == 4, (
        "baris tanpa nominal tetap baris; jangan disaring"
    )
    assert qa.aggregate(rows, AWAL, AKHIR)["jumlah_baris"] == 4


def test_rows_outside_the_period_are_not_counted():
    """Baris Oktober tidak boleh masuk hitungan Januari."""
    rows = rows_of(4) + [
        ["2025-10-05 09:00:00", "BNI", "", 1000, "Bahan Baku", "luar", "verified", "", "x1", "x.jpg", ""],
    ]
    assert qa.count_rows(rows, AWAL, AKHIR) == 4
    assert qa.aggregate(rows, AWAL, AKHIR)["jumlah_baris"] == 4


def test_rows_with_unreadable_dates_are_not_counted():
    """Tanggal tak terbaca tidak masuk periode mana pun, jadi tidak dihitung."""
    rows = rows_of(2) + [
        ["bukan tanggal", "BNI", "", 1000, "Bahan Baku", "rusak", "verified", "", "y1", "y.jpg", ""],
    ]
    assert qa.count_rows(rows, AWAL, AKHIR) == 2


# ------------------------------------------------ kesesuaian dengan pembanding

def _real_ledger():
    path = ROOT / "sc-out" / "sc08_ledger.csv"
    if not path.exists():
        return None
    import _sc08_ledger as ledger_tools

    return ledger_tools.read_ledger_csv(path)


def test_by_category_ranks_by_the_requested_direction():
    """Daftar pengeluaran diurutkan menurut keluar, bukan menurut masuk+keluar.

    `rekap` mengurutkan menurut masuk+keluar. Kalau urutan itu dipakai apa
    adanya, kategori yang besar karena pemasukan akan muncul di daftar
    pengeluaran teratas, dan jawaban "pengeluaran terbesar" menjadi salah.
    """
    rows = [
        # Pemasukan besar, pengeluaran kecil.
        ["2026-01-05 09:00:00", "BNI", 10_000_000, "", "Bagi Hasil", "masuk", "verified", "", "a", "a.jpg", ""],
        ["2026-01-06 09:00:00", "BNI", "", 100_000, "Bagi Hasil", "keluar kecil", "verified", "", "b", "b.jpg", ""],
        # Pengeluaran terbesar.
        ["2026-01-07 09:00:00", "BNI", "", 2_000_000, "Bahan Baku", "besar", "verified", "", "c", "c.jpg", ""],
        ["2026-01-08 09:00:00", "BNI", "", 900_000, "Biaya-Ongkir", "sedang", "verified", "", "d", "d.jpg", ""],
    ]
    out = asyncio.run(qa._jalankan(
        "by_category", {"period": "2026-01", "arah": "keluar"}, lambda year: rows,
    ))
    data = json.loads(out)["kategori"]

    assert [i["kategori"] for i in data[:2]] == ["Bahan Baku", "Biaya-Ongkir"], (
        "Bagi Hasil besar karena pemasukan, bukan karena pengeluaran"
    )
    assert data[0]["keluar"] == 2_000_000
    assert data[0]["masuk"] == 0, "saat arah=keluar, sisi masuk tidak ditonjolkan"


def test_by_category_amounts_include_draft_and_are_not_double_counted():
    """Nominal kategori = verified + draft, bukan salah satunya saja."""
    rows = [
        ["2026-01-05 09:00:00", "BNI", "", 700_000, "Bahan Baku", "verified", "verified", "", "a", "a.jpg", ""],
        ["2026-01-06 09:00:00", "BNI", "", 300_000, "Bahan Baku", "draft", "draft", "", "b", "b.jpg", ""],
    ]
    data = json.loads(asyncio.run(qa._jalankan(
        "by_category", {"period": "2026-01", "arah": "keluar"}, lambda year: rows,
    )))["kategori"]

    assert len(data) == 1
    assert data[0]["keluar"] == 1_000_000, "700.000 verified + 300.000 draft"
    assert data[0]["keluar_verified"] == 700_000
    assert data[0]["keluar_draft"] == 300_000


def test_by_category_keeps_categories_beyond_the_limit():
    """Memotong daftar sebelum diurutkan bisa membuang kategori terbesar.

    Balapan yang mudah terjadi: `rekap` mengurutkan menurut masuk+keluar, lalu
    dipotong. Kategori yang kecil pada urutan itu tetapi besar pada arah yang
    ditanya akan hilang sebelum sempat diurutkan ulang.
    """
    rows = []
    # 20 kategori berpemasukan SANGAT besar, sehingga di urutan `rekap` (yang
    # memakai masuk+keluar) semuanya berada di atas KatBesar. Dengan limit
    # kecil, pemotongan sebelum pengurutan akan membuang KatBesar; pemotongan
    # sesudah pengurutan tidak.
    for i in range(20):
        rows.append([f"2026-01-{i + 1:02d} 09:00:00", "BNI", 100_000_000, "", f"Kat{i:02d}", "masuk", "verified", "", f"m{i}", "m.jpg", ""])
    # Pengeluaran terbesar, tetapi totalnya (masuk+keluar) paling kecil.
    rows.append(["2026-01-25 09:00:00", "BNI", "", 50_000_000, "KatBesar", "keluar", "verified", "", "z", "z.jpg", ""])

    data = json.loads(asyncio.run(qa._jalankan(
        "by_category", {"period": "2026-01", "arah": "keluar", "limit": 1}, lambda year: rows,
    )))["kategori"]

    assert [i["kategori"] for i in data] == ["KatBesar"], (
        "kategori berpengeluaran terbesar harus tetap muncul walau limit kecil"
    )
    assert data[0]["keluar"] == 50_000_000


def test_row_count_matches_the_independent_reference():
    """Pada ledger nyata, jumlah baris harus sama dengan pembanding mandiri.

    Pembanding dihitung `_sc08_reference`, yang tidak memakai fungsi produksi
    mana pun. Kalau keduanya berbeda, salah satu salah dan angkanya tidak boleh
    dipakai untuk menilai jawaban.
    """
    rows = _real_ledger()
    if rows is None:
        pytest.skip("butuh sc-out/sc08_ledger.csv dari run SC-08")

    recs = reference.read_rows(rows)
    expected = len(reference.slice_period(recs, AWAL, AKHIR))

    assert qa.count_rows(rows, AWAL, AKHIR) == expected
    assert qa.aggregate(rows, AWAL, AKHIR)["jumlah_baris"] == expected
