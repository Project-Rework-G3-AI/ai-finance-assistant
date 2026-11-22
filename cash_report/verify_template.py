"""Verifikasi read-only template Cash Report (gaya Bizschool).

Jalankan setelah build_template.py:

    python cash_report/verify_template.py

Cek: 7 sheet sesuai urutan, header TRANSAKSI, formula inti (RECAP/YEARLY/
EXPENSE/INCOME), freeze baris, dan tidak ada #REF!/#NAME? di seluruh formula.
Tidak menulis apa pun.
"""

from __future__ import annotations

import sys
from pathlib import Path

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


def fcell(ws, r: int, c: int):
    """Nilai SEL dalam bentuk formula (bukan hasil hitung)."""
    return ws.cell(r, c, value_render_option="FORMULA").value


def main_verify() -> int:
    sid = main.CR_TEMPLATE_ID
    if not sid:
        print("CASH_REPORT_TEMPLATE_ID kosong di .env")
        return 1
    sh = main._sheets().open_by_key(sid)

    titles = [w.title for w in sh.worksheets()]
    cek("7 sheet sesuai urutan", titles == SHEETS, f"dapat: {titles}")

    ws = sh.worksheet("TRANSAKSI")
    cek("header TRANSAKSI A1:K1", ws.row_values(1)[:11] == TRANSAKSI_HEADERS,
        f"dapat: {ws.row_values(1)}")
    cek("TRANSAKSI freeze baris 1", ws.frozen_row_count == 1,
        f"dapat: {ws.frozen_row_count}")
    cek("TRANSAKSI >= 11 kolom", ws.col_count >= 11, f"dapat: {ws.col_count}")
    cek("baris data TRANSAKSI masih kosong",
        not any(str(v).strip() for v in ws.row_values(2)))

    setup = sh.worksheet("SETUP")
    header = setup.row_values(1)[:5]
    cek("SETUP 5 kolom kategori",
        header == ["KANTONG", "KATEGORI PENDAPATAN", "KATEGORI NERACA",
                   "KATEGORI PENGELUARAN", "KATEGORI LAIN"],
        f"dapat: {header}")

    # Setiap kategori harus muncul TEPAT SEKALI. Duplikat antar kolom pernah
    # terjadi: "Transfer Antar Bank" masuk kolom pendapatan sekaligus
    # pengeluaran, sehingga admin melihatnya dua kali dengan makna berbeda.
    isi_setup = []
    for kolom in range(2, 6):
        for r in range(2, 60):
            v = setup.cell(r, kolom).value
            if isinstance(v, str) and v.strip():
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
    isi_dropdown = [setup.cell(r, BT.KOL_DROPDOWN + 1).value
                    for r in range(awal, akhir + 1)]
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

    recap = sh.worksheet("RECAP OVERVIEW")
    cek("RECAP B3 formula DATE", str(fcell(recap, 3, 2)).startswith("=DATE("),
        f"dapat: {fcell(recap, 3, 2)}")
    cek("RECAP B4 formula EOMONTH", "EOMONTH" in str(fcell(recap, 4, 2)),
        f"dapat: {fcell(recap, 4, 2)}")
    cek("RECAP C6 SUMIFS excludes transfer", "SUMIFS" in str(fcell(recap, 6, 3))
        and "Transfer Antar Bank" in str(fcell(recap, 6, 3)),
        f"dapat: {fcell(recap, 6, 3)}")

    acc = sh.worksheet("ACCOUNT")
    cek("ACCOUNT C4 SUMIFS", "SUMIFS" in str(fcell(acc, 4, 3)),
        f"dapat: {fcell(acc, 4, 3)}")

    yr = sh.worksheet("YEARLY OVERVIEW")
    cek("YEARLY B5 DATE dari Dimulai", "YEAR($B$3)" in str(fcell(yr, 5, 2)),
        f"dapat: {fcell(yr, 5, 2)}")
    cek("YEARLY B6 SUMIFS per bulan", "EOMONTH" in str(fcell(yr, 6, 2)),
        f"dapat: {fcell(yr, 6, 2)}")

    exp = sh.worksheet("EXPENSE DETAIL")
    cek("EXPENSE B6 SUMIFS", "SUMIFS" in str(fcell(exp, 6, 2)),
        f"dapat: {fcell(exp, 6, 2)}")
    cek(f"EXPENSE A{EXP_TOTAL_ROW} TOTAL PENGELUARAN",
        str(exp.cell(EXP_TOTAL_ROW, 1).value) == "TOTAL PENGELUARAN",
        f"dapat: {exp.cell(EXP_TOTAL_ROW, 1).value}")
    cek(f"EXPENSE B{COGS_ROW} COGS aman dari sel kosong",
        "COUNT" in str(fcell(exp, COGS_ROW, 2)),
        f"dapat: {fcell(exp, COGS_ROW, 2)}")

    inc = sh.worksheet("INCOME STATEMENT")
    cek("INCOME A12 LABA BERSIH", str(inc.cell(12, 1).value) == "LABA BERSIH",
        f"dapat: {inc.cell(12, 1).value}")
    cek("INCOME B12 formula", str(fcell(inc, 12, 2)).startswith("="),
        f"dapat: {fcell(inc, 12, 2)}")

    rusak = []
    for w in sh.worksheets():
        for row in w.get_all_values():
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
