"""Verifikasi read-only template Cash Report (gaya Bizschool).

Jalankan setelah build_template.py:

    python cash_report/verify_template.py

Cek: 7 sheet sesuai urutan, header TRANSAKSI, formula inti (RECAP/YEARLY/
EXPENSE/INCOME), freeze baris, dan tidak ada #REF!/#NAME? di seluruh formula.
Tidak menulis apa pun.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import gspread

sys.path.insert(0, str(Path(__file__).parent.parent))

import main  # noqa: E402
from cash_report import build_template as BT  # noqa: E402
from cash_report import categories as KAT  # noqa: E402

# Posisi baris EXPENSE DETAIL dihitung dari daftar kategori, bukan angka mati,
# supaya verifikasi tidak patah saat daftar kategori berubah.
_KAT_BEBAN = KAT.PENGELUARAN_SOP + KAT.PENGELUARAN_TAMBAHAN
EXP_TOTAL_ROW = 6 + len(_KAT_BEBAN)   # baris TOTAL PENGELUARAN
COGS_ROW = EXP_TOTAL_ROW + 6          # memo dimulai +2, COGS 4 baris setelahnya

SHEETS = [
    "SETUP", "ACCOUNT", "TRANSAKSI", "RECAP OVERVIEW",
    "YEARLY OVERVIEW", "EXPENSE DETAIL", "INCOME STATEMENT",
]
TRANSAKSI_HEADERS = [
    "Tanggal", "Kantong", "Masuk", "Keluar", "Kategori", "Keterangan",
    "Status", "Catatan", "Ref ID", "Sumber File", "Link Bukti",
]

gagal: list[str] = []


def cek(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'OK ' if ok else 'GAGAL'}] {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        gagal.append(label)


def baca_blok(ws) -> list[list[str]]:
    """Seluruh isi sheet dalam SATU panggilan API.

    ws.cell() melakukan satu request HTTP per sel. Kuota Sheets hanya 60 read
    per menit per pengguna, sehingga memeriksa 4 kolom x 58 baris seperti
    sebelumnya langsung memicu 429. get_all_values() mengambil seluruh sheet
    sekali, berapa pun jumlah selnya.
    """
    return ws.get_all_values()


def sel(blok: list[list[str]], r: int, c: int) -> str:
    """Ambil sel dari hasil baca_blok. r dan c 1-based seperti di Sheets."""
    if r - 1 < len(blok):
        baris = blok[r - 1]
        if c - 1 < len(baris):
            return baris[c - 1]
    return ""


def _coba_ulang(fn, *a, **kw):
    """Jalankan fn, tunggu lalu ulangi bila kena 429 kuota Sheets."""
    for percobaan in (1, 2, 3):
        try:
            return fn(*a, **kw)
        except gspread.exceptions.APIError as exc:
            if "429" not in str(exc) or percobaan == 3:
                raise
            jeda = 30 * percobaan
            print(f"  kuota Sheets tercapai, menunggu {jeda} detik "
                  f"(percobaan {percobaan}/3)...")
            time.sleep(jeda)


def main_verify() -> int:
    sid = main.CR_TEMPLATE_ID
    if not sid:
        print("CASH_REPORT_TEMPLATE_ID kosong di .env")
        return 1
    sh = main._sheets().open_by_key(sid)

    titles = [w.title for w in sh.worksheets()]
    cek("7 sheet sesuai urutan", titles == SHEETS, f"dapat: {titles}")

    # Satu baca per sheet. row_values() dan cell() masing-masing satu request
    # HTTP, sehingga versi lama menghabiskan belasan read hanya untuk beberapa
    # sel dan menabrak kuota 60 read/menit.
    ws = sh.worksheet("TRANSAKSI")
    data_ws = _coba_ulang(baca_blok, ws)
    baris1 = data_ws[0] if data_ws else []
    baris2 = data_ws[1] if len(data_ws) > 1 else []
    cek("header TRANSAKSI A1:K1", baris1[:11] == TRANSAKSI_HEADERS,
        f"dapat: {baris1[:11]}")
    cek("TRANSAKSI freeze baris 1", ws.frozen_row_count == 1,
        f"dapat: {ws.frozen_row_count}")
    cek("TRANSAKSI >= 11 kolom", ws.col_count >= 11, f"dapat: {ws.col_count}")
    cek("baris data TRANSAKSI masih kosong",
        not any(str(v).strip() for v in baris2))

    setup = sh.worksheet("SETUP")
    data = _coba_ulang(baca_blok, setup)

    # Header ada di baris 3, BUKAN baris 1. Baris 1 adalah judul sheet dan
    # baris 2 kosong, jadi memakai baris 1 membuat pemeriksaan ini selalu
    # gagal dengan pesan yang membingungkan.
    header = [sel(data, BT.BARIS_HEADER, c) for c in range(1, 6)]
    cek("SETUP header 5 kolom kategori",
        header == ["KANTONG", "KATEGORI PENDAPATAN", "KATEGORI NERACA",
                   "KATEGORI PENGELUARAN", "KATEGORI LAIN"],
        f"dapat: {header}")

    # Setiap kategori harus muncul TEPAT SEKALI. Duplikat antar kolom pernah
    # terjadi: "Transfer Antar Bank" masuk kolom pendapatan sekaligus
    # pengeluaran, sehingga admin melihatnya dua kali dengan makna berbeda.
    isi_setup = []
    for kolom in range(2, 6):
        for r in range(BT.BARIS_HEADER + 1, BT.BARIS_HEADER + 30):
            v = sel(data, r, kolom)
            if v.strip():
                isi_setup.append(v.strip())
    dobel = sorted({k for k in isi_setup if isi_setup.count(k) > 1})
    cek("SETUP tidak ada kategori duplikat", not dobel, f"duplikat: {dobel}")

    hilang_setup = [k for k in KAT.KATEGORI if k not in isi_setup]
    cek("SETUP memuat semua kategori", not hilang_setup,
        f"hilang: {hilang_setup}")

    # Sumber dropdown di SETUP harus memuat seluruh kategori, berurutan, tanpa
    # sel kosong. Sel kosong di tengah rentang muncul sebagai pilihan kosong.
    awal = BT.BARIS_AWAL_DROPDOWN
    akhir = awal + len(BT.KAT_DROPDOWN) - 1
    kol = BT._col_letter(BT.KOL_DROPDOWN)
    isi_dropdown = [sel(data, r, BT.KOL_DROPDOWN + 1) for r in range(awal, akhir + 1)]
    cek("SETUP sumber dropdown lengkap",
        isi_dropdown == list(KAT.KATEGORI),
        f"dapat {sum(1 for x in isi_dropdown if x)} dari {len(KAT.KATEGORI)}")

    # Kolom Kategori di TRANSAKSI harus punya validasi yang menunjuk rentang itu.
    # gspread tidak menyediakannya, jadi dibaca lewat Sheets API langsung.
    grid = main._sheets().spreadsheets().get(
        spreadsheetId=sid,
        ranges=["TRANSAKSI!E2"],
        includeGridData=True,
        fields="sheets(data(rowData(values(dataValidation))))",
    ).execute()
    dv, kondisi, rentang = None, {}, ""
    try:
        dv = (grid["sheets"][0]["data"][0]["rowData"][0]["values"][0]
              ["dataValidation"])
        kondisi = dv.get("condition", {})
        rentang = (kondisi.get("values") or [{}])[0].get("userEnteredValue", "")
    except (KeyError, IndexError):
        pass
    cek("TRANSAKSI kolom E punya dropdown",
        dv is not None and kondisi.get("type") == "ONE_OF_RANGE",
        f"dapat: {dv}")
    cek("dropdown menunjuk daftar di SETUP",
        f"SETUP!${kol}" in str(rentang),
        f"dapat: {rentang}")

    # Formula dibaca dengan satu panggilan per sheet, lalu diambil per sel
    # dari hasilnya. Hasilnya di-cache supaya sheet yang sama tidak dibaca dua
    # kali: pemeriksaan #REF! di bawah juga memakai cache ini.
    _cache: dict[str, list[list[str]]] = {}

    def formula(sheet: str) -> list[list[str]]:
        if sheet not in _cache:
            _cache[sheet] = _coba_ulang(
                sh.worksheet(sheet).get_all_values,
                value_render_option="FORMULA")
        return _cache[sheet]

    recap = formula("RECAP OVERVIEW")
    cek("RECAP B3 formula DATE", sel(recap, 3, 2).startswith("=DATE("),
        f"dapat: {sel(recap, 3, 2)}")
    cek("RECAP B4 formula EOMONTH", "EOMONTH" in sel(recap, 4, 2),
        f"dapat: {sel(recap, 4, 2)}")
    cek("RECAP C6 SUMIFS excludes transfer",
        "SUMIFS" in sel(recap, 6, 3)
        and "Transfer Antar Bank" in sel(recap, 6, 3),
        f"dapat: {sel(recap, 6, 3)}")

    acc = formula("ACCOUNT")
    cek("ACCOUNT C4 SUMIFS", "SUMIFS" in sel(acc, 4, 3),
        f"dapat: {sel(acc, 4, 3)}")

    yr = formula("YEARLY OVERVIEW")
    cek("YEARLY B5 DATE dari Dimulai", "YEAR($B$3)" in sel(yr, 5, 2),
        f"dapat: {sel(yr, 5, 2)}")
    cek("YEARLY B6 SUMIFS per bulan", "EOMONTH" in sel(yr, 6, 2),
        f"dapat: {sel(yr, 6, 2)}")

    exp = formula("EXPENSE DETAIL")
    cek("EXPENSE B6 SUMIFS", "SUMIFS" in sel(exp, 6, 2),
        f"dapat: {sel(exp, 6, 2)}")
    cek(f"EXPENSE A{EXP_TOTAL_ROW} TOTAL PENGELUARAN",
        sel(exp, EXP_TOTAL_ROW, 1) == "TOTAL PENGELUARAN",
        f"dapat: {sel(exp, EXP_TOTAL_ROW, 1)}")
    cek(f"EXPENSE B{COGS_ROW} COGS aman dari sel kosong",
        "COUNT" in sel(exp, COGS_ROW, 2),
        f"dapat: {sel(exp, COGS_ROW, 2)}")

    inc = formula("INCOME STATEMENT")
    cek("INCOME A12 LABA BERSIH", sel(inc, 12, 1) == "LABA BERSIH",
        f"dapat: {sel(inc, 12, 1)}")
    cek("INCOME B12 formula", sel(inc, 12, 2).startswith("="),
        f"dapat: {sel(inc, 12, 2)}")

    # Semua isi sudah ada di _cache (SETUP dan TRANSAKSI diisi di atas), jadi
    # pemeriksaan ini tidak menambah request baru.
    _cache.setdefault("SETUP", data)
    _cache.setdefault("TRANSAKSI", data_ws)
    rusak = []
    for w in sh.worksheets():
        for row in formula(w.title):
            for v in row:
                if isinstance(v, str) and ("#REF!" in v or "#NAME?" in v):
                    rusak.append(f"{w.title}: {v[:60]}")
    cek("tidak ada #REF!/#NAME?", not rusak, "; ".join(rusak[:3]))

    print()
    if gagal:
        print(f"VERIFIKASI GAGAL ({len(gagal)}): " + ", ".join(gagal))
        return 1
    print("VERIFIKASI LULUS — semua pemeriksaan OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_verify())
