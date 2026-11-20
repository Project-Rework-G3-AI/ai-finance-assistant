"""Bangun template Google Sheet 'Cash Report TEMPLATE' (gaya Bizschool, year-agnostic).

Sekali jalan. Jalankan dari folder bot dengan .env terisi (CASH_REPORT_FOLDER_ID,
OAuth + service account):

    python cash_report/build_template.py

Menghasilkan 7 sheet:
  SETUP | ACCOUNT | TRANSAKSI | RECAP OVERVIEW | YEARLY OVERVIEW |
  EXPENSE DETAIL | INCOME STATEMENT

TRANSAKSI = flat ledger (bot append baris); sheet lain berformula otomatis.
Semua isi ditulis per-BLOCK (bukan per sel) agar aman dari kuota Write API.
Print id spreadsheet -> salin ke CASH_REPORT_TEMPLATE_ID (.env & Render).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import main  # noqa: E402  (memakai koneksi Drive OAuth + SA dari .env)

SHEETS = [
    "SETUP", "ACCOUNT", "TRANSAKSI", "RECAP OVERVIEW",
    "YEARLY OVERVIEW", "EXPENSE DETAIL", "INCOME STATEMENT",
]

KANTONG = ["BRI", "BNI", "Jago", "UANG KAS"]
KAT_INCOME = ["Penjualan", "Transfer Antar Bank", "Lainnya"]
KAT_EXPENSE = [
    "Bahan Baku", "Biaya-Gaji Karyawan", "Biaya-Konsumsi",
    "Biaya-Perlengkapan Kantor dan Administrasi", "Biaya-Transportasi",
    "Biaya-Ongkir", "Biaya-Perbaikan Bangunan", "Biaya-Operasional",
    "Biaya-Pembelian Aset", "Biaya-Sosial", "Administrasi Bank", "Pajak",
    "Bunga", "Admin Flip", "Transfer Antar Bank", "Lainnya",
]
# Kategori pengeluaran tanpa Transfer Antar Bank (dipakai EXPENSE DETAIL & PnL)
KAT_NO_TF = [k for k in KAT_EXPENSE if k != "Transfer Antar Bank"]
# Posisi baris EXPENSE DETAIL: kategori mulai baris 6 (tanpa Transfer)
EXP_ROW = {k: 6 + i for i, k in enumerate(KAT_NO_TF)}  # Bahan Baku=6, Pajak=17, Bunga=18
EXP_TOTAL_ROW = 6 + len(KAT_NO_TF)  # 21

TRANSAKSI_HEADERS = [
    "Tanggal", "Kantong", "Masuk", "Keluar", "Kategori", "Keterangan",
    "Status", "Catatan", "Ref ID", "Sumber File", "Link Bukti",
]

MONTH_COLS = list("BCDEFGHIJKLM")


def put(ws, start: str, matrix: list[list]) -> None:
    """Tulis block matrix dari sel kiri-atas (satu request)."""
    ws.update(values=matrix, range_name=start, value_input_option="USER_ENTERED")


def build() -> str:
    if not main.CR_FOLDER_ID:
        raise SystemExit("CASH_REPORT_FOLDER_ID kosong di .env")

    year_folder = main._find_or_create_folder("TEMPLATE", main.CR_FOLDER_ID)
    q = (
        "name = 'Cash Report TEMPLATE' and '" + year_folder + "' in parents "
        "and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    )
    ada = main._drive().files().list(q=q, fields="files(id)", pageSize=10).execute().get("files", [])
    if ada:
        raise SystemExit(f"'Cash Report TEMPLATE' sudah ada ({ada[0]['id']}) — hapus dulu bila ingin membangun ulang.")

    f = main._drive().files().create(
        body={
            "name": "Cash Report TEMPLATE",
            "mimeType": "application/vnd.google-apps.spreadsheet",
            "parents": [year_folder],
        },
        fields="id, webViewLink",
    ).execute()
    sid = f["id"]
    sh = main._sheets().open_by_key(sid)

    sh.add_worksheet(title="SETUP", rows=60, cols=10)
    sh.del_worksheet(sh.sheet1)  # sheet default "Sheet1"
    for name in SHEETS[1:]:
        sh.add_worksheet(title=name, rows=200, cols=20)
    sheets = {w.title: w for w in sh.worksheets()}

    _setup(sheets["SETUP"])
    _account(sheets["ACCOUNT"])
    _transaksi(sheets["TRANSAKSI"])
    _recap(sheets["RECAP OVERVIEW"])
    _yearly(sheets["YEARLY OVERVIEW"])
    _expense(sheets["EXPENSE DETAIL"])
    _income(sheets["INCOME STATEMENT"])
    _format(sh, sheets)

    print("TEMPLATE DIBUAT")
    print("id:", sid)
    print("url:", f.get("webViewLink", ""))
    print("Salin id ke CASH_REPORT_TEMPLATE_ID (.env lokal & Dashboard Render).")
    return sid


# ---------- isi sheet ----------

def _setup(ws) -> None:
    put(ws, "A1", [["⚙️ SETUP — daftar kantong & kategori (edit sesuai kebutuhan)"]])
    rows = [["KANTONG", "KATEGORI PENDAPATAN", "KATEGORI PENGELUARAN"]]
    for i in range(max(len(KANTONG), len(KAT_INCOME), len(KAT_EXPENSE))):
        rows.append([
            KANTONG[i] if i < len(KANTONG) else "",
            KAT_INCOME[i] if i < len(KAT_INCOME) else "",
            KAT_EXPENSE[i] if i < len(KAT_EXPENSE) else "",
        ])
    put(ws, "A3", rows)
    put(ws, "A21", [["Kantong = kantong uang perusahaan: BRI, BNI, Jago, UANG KAS.\n"
                     "UANG KAS = kas operasional (tunai). Antar-bank via FLIP tetap dicatat\n"
                     "dari kantong asal + kategori Admin Flip untuk biayanya."]])


def _account(ws) -> None:
    put(ws, "A1", [["💳 ACCOUNT — saldo per kantong"]])
    rows = [["Kantong", "Saldo Awal", "Masuk", "Keluar", "Saldo Akhir"]]
    for i in range(4):
        r = 4 + i
        rows.append([
            f"=SETUP!A{4 + i}", "",
            f"=SUMIFS(TRANSAKSI!C:C,TRANSAKSI!B:B,$A{r})",
            f"=SUMIFS(TRANSAKSI!D:D,TRANSAKSI!B:B,$A{r})",
            f"=B{r}+C{r}-D{r}",
        ])
    rows.append(["TOTAL", "=SUM(B4:B7)", "=SUM(C4:C7)", "=SUM(D4:D7)", "=SUM(E4:E7)"])
    put(ws, "A3", rows)
    put(ws, "G3", [["Saldo Awal diisi MANUAL (saldo awal tahun tiap kantong).\n"
                    "Masuk/Keluar otomatis dari TRANSAKSI — termasuk baris transfer,\n"
                    "sehingga saldo tiap kantong akurat."]])


def _transaksi(ws) -> None:
    put(ws, "A1", [TRANSAKSI_HEADERS])


def _recap(ws) -> None:
    put(ws, "A1", [["📊 RECAP OVERVIEW — rentang periode bisa diedit"]])
    put(ws, "A3", [
        ["Dimulai", "=DATE(2026,1,1)"],
        ["Berakhir", "=EOMONTH(B3,11)"],
    ])
    rng = 'TRANSAKSI!A:A,">="&$B$3,TRANSAKSI!A:A,"<="&$B$4'
    put(ws, "A6", [
        ["Pendapatan", "", f'=SUMIFS(TRANSAKSI!C:C,{rng},TRANSAKSI!E:E,"<>Transfer Antar Bank")'],
        ["Pengeluaran", "", f'=SUMIFS(TRANSAKSI!D:D,{rng},TRANSAKSI!E:E,"<>Transfer Antar Bank")'],
        ["Selisih (Surplus/Defisit)", "", "=C6-C7"],
    ])
    put(ws, "A10", [["PENDAPATAN PER KATEGORI"], ["Kategori", "Jumlah"]])
    inc = [[f"=SETUP!B{4 + i}",
            f'=SUMIFS(TRANSAKSI!C:C,TRANSAKSI!E:E,$A{12 + i},{rng})']
           for i in range(len(KAT_INCOME))]
    put(ws, "A12", inc)

    put(ws, "A16", [["PENGELUARAN PER KATEGORI (tanpa Transfer Antar Bank)"],
                    ["Kategori", "Jumlah"]])
    exp = []
    r = 18
    for i, k in enumerate(KAT_EXPENSE):
        if k == "Transfer Antar Bank":
            continue
        exp.append([f"=SETUP!C{4 + i}",
                    f'=SUMIFS(TRANSAKSI!D:D,TRANSAKSI!E:E,$A{r},{rng})'])
        r += 1
    exp.append(["TOTAL PENGELUARAN", f"=SUM(B18:B{r - 1})"])
    put(ws, "A18", exp)


def _yearly(ws) -> None:
    put(ws, "A1", [["📅 YEARLY OVERVIEW — arus kas 12 bulan (otomatis)"]])
    put(ws, "A3", [["Dimulai", "='RECAP OVERVIEW'!B3"]])
    head = ["Bulan"] + [f"=DATE(YEAR($B$3),{m},1)" for m in range(1, 13)] + ["Total"]
    tf = ',TRANSAKSI!E:E,"<>Transfer Antar Bank"'
    pend = ["Pendapatan"]
    peng = ["Pengeluaran"]
    for i, c in enumerate(MONTH_COLS):
        pend.append(
            f'=SUMIFS(TRANSAKSI!C:C,TRANSAKSI!A:A,">="&{c}$5,'
            f'TRANSAKSI!A:A,"<="&EOMONTH({c}$5,0){tf})')
        peng.append(
            f'=SUMIFS(TRANSAKSI!D:D,TRANSAKSI!A:A,">="&{c}$5,'
            f'TRANSAKSI!A:A,"<="&EOMONTH({c}$5,0){tf})')
    pend.append("=SUM(B6:M6)")
    peng.append("=SUM(B7:M7)")
    sel = ["Selisih"] + [f"={c}6-{c}7" for c in MONTH_COLS] + ["=N6-N7"]
    put(ws, "A5", [head, pend, peng, sel])


def _expense(ws) -> None:
    put(ws, "A1", [["🧮 EXPENSE DETAIL — per kategori per bulan (otomatis)"]])
    put(ws, "A3", [["Bulan"] + [f"='YEARLY OVERVIEW'!{c}5" for c in MONTH_COLS] + ["Total"]])
    put(ws, "A5", [["PER KATEGORI DARI TRANSAKSI (tanpa Transfer Antar Bank)"]])
    rows = []
    for k in KAT_NO_TF:
        r = EXP_ROW[k]
        rows.append(
            [f"=SETUP!C{4 + KAT_EXPENSE.index(k)}"]
            + [f'=SUMIFS(TRANSAKSI!D:D,TRANSAKSI!E:E,$A{r},'
               f'TRANSAKSI!A:A,">="&{c}$3,TRANSAKSI!A:A,"<="&EOMONTH({c}$3,0))'
               for c in MONTH_COLS]
            + [f"=SUM(B{r}:M{r})"])
    rows.append(["TOTAL PENGELUARAN"]
                + [f"=SUM({c}6:{c}{EXP_TOTAL_ROW - 1})" for c in MONTH_COLS]
                + [f"=SUM(N6:N{EXP_TOTAL_ROW - 1})"])
    put(ws, "A6", rows)

    memo = EXP_TOTAL_ROW + 2  # 23
    m = [
        ["MEMO — COST OF GOODS SOLD (opsional, isi manual)"] + [""] * 13,
        ["Beginning Inventory"] + [""] * 13,
        ["(+) Purchase"] + [""] * 13,
        ["(-) Ending Inventory"] + [""] * 13,
        ["Cost of Goods Sold"]
        + [f'=IF(COUNT({c}{memo + 1}:{c}{memo + 3})<3,"",'
           f"{c}{memo + 1}+{c}{memo + 2}-{c}{memo + 3})" for c in MONTH_COLS]
        + [f"=SUM(B{memo + 4}:M{memo + 4})"],
    ]
    put(ws, f"A{memo}", m)


def _income(ws) -> None:
    put(ws, "A1", [["📑 INCOME STATEMENT — laba rugi per bulan (otomatis)"]])
    put(ws, "A3", [["Bulan"] + [f"='YEARLY OVERVIEW'!{c}5" for c in MONTH_COLS] + ["Total"]])
    T, BB, PJ, BG = EXP_TOTAL_ROW, EXP_ROW["Bahan Baku"], EXP_ROW["Pajak"], EXP_ROW["Bunga"]
    tpl = [
        ("PENDAPATAN", "='YEARLY OVERVIEW'!{c}6"),
        ("(-) HPP / Bahan Baku", f"='EXPENSE DETAIL'!{{c}}{BB}"),
        ("LABA KOTOR", "={c}5-{c}6"),
        ("(-) Beban Operasional",
         f"='EXPENSE DETAIL'!{{c}}{T}-'EXPENSE DETAIL'!{{c}}{BB}"
         f"-'EXPENSE DETAIL'!{{c}}{PJ}-'EXPENSE DETAIL'!{{c}}{BG}"),
        ("LABA SEBELUM PAJAK", "={c}7-{c}8"),
        ("(-) Pajak", f"='EXPENSE DETAIL'!{{c}}{PJ}"),
        ("(-) Bunga", f"='EXPENSE DETAIL'!{{c}}{BG}"),
        ("LABA BERSIH", "={c}9-{c}10-{c}11"),
    ]
    rows = [[label] + [t.format(c=c) for c in MONTH_COLS] + [t.format(c="N")]
            for label, t in tpl]
    put(ws, "A5", rows)


# ---------- format ----------

def _format(sh, sheets: dict) -> None:
    bold = {"textFormat": {"bold": True}}
    money = {"numberFormat": {"type": "NUMBER", "pattern": '"Rp"#,##0'}}
    date_fmt = {"numberFormat": {"type": "DATE", "pattern": "d-mmm-yy"}}
    month_fmt = {"numberFormat": {"type": "DATE", "pattern": "mmm"}}
    header_bg = {"backgroundColor": {"red": 0.85, "green": 0.9, "blue": 0.95}}

    def req(title, r0, r1, c0, c1, fmt, fields):
        return {"repeatCell": {
            "range": {"sheetId": sheets[title].id, "startRowIndex": r0, "endRowIndex": r1,
                      "startColumnIndex": c0, "endColumnIndex": c1},
            "cell": {"userEnteredFormat": fmt}, "fields": fields,
        }}

    reqs = [
        *[
            {"updateSheetProperties": {
                "properties": {"sheetId": w.id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }}
            for w in sh.worksheets()
        ],
        req("TRANSAKSI", 0, 1, 0, 11, bold, "userEnteredFormat.textFormat.bold"),
        req("TRANSAKSI", 0, 1, 0, 11, header_bg, "userEnteredFormat.backgroundColor"),
        req("TRANSAKSI", 1, 5000, 0, 1, date_fmt, "userEnteredFormat.numberFormat"),
        req("TRANSAKSI", 1, 5000, 2, 4, money, "userEnteredFormat.numberFormat"),
        req("SETUP", 2, 3, 0, 3, bold, "userEnteredFormat.textFormat.bold"),
        req("ACCOUNT", 2, 3, 0, 5, bold, "userEnteredFormat.textFormat.bold"),
        req("ACCOUNT", 3, 9, 1, 5, money, "userEnteredFormat.numberFormat"),
        req("RECAP OVERVIEW", 5, 8, 0, 3, bold, "userEnteredFormat.textFormat.bold"),
        req("RECAP OVERVIEW", 5, 34, 1, 2, money, "userEnteredFormat.numberFormat"),
        req("YEARLY OVERVIEW", 4, 5, 0, 14, bold, "userEnteredFormat.textFormat.bold"),
        req("YEARLY OVERVIEW", 4, 5, 1, 13, month_fmt, "userEnteredFormat.numberFormat"),
        req("YEARLY OVERVIEW", 5, 8, 1, 14, money, "userEnteredFormat.numberFormat"),
        req("EXPENSE DETAIL", 2, 3, 0, 14, bold, "userEnteredFormat.textFormat.bold"),
        req("EXPENSE DETAIL", 5, EXP_TOTAL_ROW, 1, 14, money, "userEnteredFormat.numberFormat"),
        req("INCOME STATEMENT", 2, 3, 0, 14, bold, "userEnteredFormat.textFormat.bold"),
        req("INCOME STATEMENT", 4, 12, 1, 14, money, "userEnteredFormat.numberFormat"),
        req("INCOME STATEMENT", 11, 12, 0, 14, bold, "userEnteredFormat.textFormat.bold"),  # LABA BERSIH
        req("INCOME STATEMENT", 6, 7, 0, 1, bold, "userEnteredFormat.textFormat.bold"),      # LABA KOTOR
        req("INCOME STATEMENT", 8, 9, 0, 1, bold, "userEnteredFormat.textFormat.bold"),      # LABA SEBELUM PAJAK
    ]
    widths = [100, 90, 110, 110, 200, 260, 80, 240, 150, 170, 200]
    for i, w in enumerate(widths):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sheets["TRANSAKSI"].id, "dimension": "COLUMNS",
                      "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": w}, "fields": "pixelSize",
        }})
    sh.batch_update({"requests": reqs})


if __name__ == "__main__":
    build()
