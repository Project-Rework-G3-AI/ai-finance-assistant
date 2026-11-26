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

from cash_report import categories as KAT  # noqa: E402  (daftar kategori tunggal)

KANTONG = ["BRI", "BNI", "Jago", "UANG KAS"]

# Setiap kategori menempati TEPAT SATU kolom di SETUP. Sebelumnya
# "Transfer Antar Bank" masuk dua kolom sekaligus (pendapatan dan pengeluaran),
# sehingga admin melihatnya dua kali di dropdown dengan makna berbeda.
KAT_INCOME = list(KAT.PENDAPATAN)

# Kolom pengeluaran hanya berisi beban sungguhan. Transfer Antar Bank bukan
# beban, dan penanda bukan kategori akuntansi: keduanya pindah ke kolom sendiri.
KAT_EXPENSE = KAT.PENGELUARAN_SOP + KAT.PENGELUARAN_TAMBAHAN

# Perpindahan dana dan penanda internal: bukan pendapatan, bukan beban, bukan
# neraca. Tetap butuh tempat agar baris TRANSAKSI bisa memakainya.
KAT_LAIN = list(KAT.PERPINDAHAN) + [KAT.PERLU_DITINJAU]

# Sumber dropdown kolom Kategori di TRANSAKSI: satu kolom berisi SELURUH
# kategori secara berurutan tanpa sel kosong. Kolom B-E di SETUP sengaja
# berkelompok dan panjangnya tidak sama, sehingga tidak bisa dipakai langsung
# sebagai rujukan validasi: sel kosong di tengahnya akan muncul sebagai pilihan
# kosong di dropdown.
KAT_DROPDOWN = list(KAT.KATEGORI)
KOL_DROPDOWN = 5          # indeks 0-based: kolom F di SETUP
BARIS_HEADER = 3          # header tabel SETUP (baris 1 judul, baris 2 kosong)
BARIS_AWAL_DROPDOWN = 4   # baris 4, tepat di bawah header baris 3
BARIS_VALIDASI = 5000     # sejauh mana kolom TRANSAKSI diberi dropdown

# Kategori neraca: bukan pendapatan dan bukan beban, jadi tidak masuk RECAP
# maupun laba rugi. Tetap ditampung di SETUP agar cocok dengan daftar model.
# Saldo Awal ikut di sini: bukan transaksi, tetapi diisi admin sebagai baris
# pembuka, jadi harus tersedia di dropdown.
KAT_NERACA = KAT.SALDO_AWAL + KAT.NERACA

# EXPENSE DETAIL & laba rugi hanya memuat beban sungguhan: Transfer Antar Bank
# dan Perlu Ditinjau dikecualikan.
KAT_NO_TF = KAT.PENGELUARAN_SOP + KAT.PENGELUARAN_TAMBAHAN
EXP_ROW = {k: 6 + i for i, k in enumerate(KAT_NO_TF)}
EXP_TOTAL_ROW = 6 + len(KAT_NO_TF)

TRANSAKSI_HEADERS = [
    "Tanggal", "Kantong", "Masuk", "Keluar", "Kategori", "Keterangan",
    "Status", "Catatan", "Ref ID", "Sumber File", "Link Bukti",
]

MONTH_COLS = list("BCDEFGHIJKLM")


def put(ws, start: str, matrix: list[list]) -> None:
    """Tulis block matrix dari sel kiri-atas (satu request)."""
    ws.update(values=matrix, range_name=start, value_input_option="USER_ENTERED")


def _force_locale(sh) -> None:
    """Set locale spreadsheet ke en_US sebelum formula ditulis.

    Formula di file ini memakai koma sebagai pemisah argumen. Google Sheets
    mem-parse formula sesuai locale spreadsheet, jadi locale Indonesia
    (in_ID) membacanya sebagai parse error -> seluruh sel berformula #ERROR!.
    Locale harus diset sebelum penulisan pertama, bukan sesudah.
    """
    try:
        sh.update_locale("en_US")
    except Exception as exc:  # pragma: no cover - hanya jalur kegagalan API
        raise SystemExit(f"Gagal set locale spreadsheet ke en_US: {exc}") from exc


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

    # SA tidak bisa membuat file (kuota 0) — bootstrap lewat Apps Script.
    f = main.apps_script_call(
        "create_sheet", {"name": "Cash Report TEMPLATE", "parent_id": year_folder}
    )
    sid = f["id"]
    sh = main._sheets().open_by_key(sid)

    # Locale harus diset sebelum sel berformula ditulis: Google Sheets mem-parse
    # formula sesuai locale, dan formula di sini memakai koma.
    _force_locale(sh)

    sh.add_worksheet(title="SETUP", rows=60, cols=10)  # 6 kolom terpakai
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

def _col_letter(idx: int) -> str:
    """Indeks kolom 0-based -> huruf kolom (0 -> A, 5 -> F)."""
    return chr(ord("A") + idx) if idx < 26 else f"A{chr(ord('A') + idx - 26)}"


def _validasi_dropdown(sheet_id: int) -> dict:
    """Request setDataValidation untuk kolom Kategori di TRANSAKSI.

    Nilai dropdown diambil dari rentang SETUP, bukan ditulis sebagai daftar
    inline: batas panjang daftar inline sekitar 256 karakter, sedangkan 31
    kategori sudah lebih panjang. Rentang juga membuat perubahan daftar di
    SETUP langsung berlaku tanpa menyentuh validasinya.
    """
    return {"setDataValidation": {
        "range": {
            "sheetId": sheet_id,
            "startRowIndex": 1,              # baris 2 (baris 1 = header)
            "endRowIndex": BARIS_VALIDASI,
            "startColumnIndex": 4,           # kolom E (indeks 0-based)
            "endColumnIndex": 5,
        },
        "rule": {
            "condition": {
                "type": "ONE_OF_RANGE",
                "values": [{"userEnteredValue": "=SETUP!${kol}${awal}:${kol}${akhir}".format(
                    kol=_col_letter(KOL_DROPDOWN),
                    awal=BARIS_AWAL_DROPDOWN,
                    akhir=BARIS_AWAL_DROPDOWN + len(KAT_DROPDOWN) - 1,
                )}],
            },
            "strict": False,   # nilai lama di luar daftar tidak dianggap galat
            "showCustomUi": True,
        },
    }}


def _setup(ws) -> None:
    put(ws, "A1", [["⚙️ SETUP — daftar kantong & kategori (edit sesuai kebutuhan)"]])
    # Lima kolom: kantong, pendapatan, neraca, pengeluaran, dan kategori lain.
    # Neraca dipisah dari pengeluaran karena Persediaan/Aset Tetap/Utang-Piutang
    # bukan beban dan tidak boleh masuk EXPENSE DETAIL maupun laba rugi.
    # Kategori lain menampung perpindahan dana dan penanda internal, supaya
    # setiap kategori muncul tepat sekali dan admin tidak melihat duplikat.
    rows = [["KANTONG", "KATEGORI PENDAPATAN", "KATEGORI NERACA",
             "KATEGORI PENGELUARAN", "KATEGORI LAIN"]]
    n = max(len(KANTONG), len(KAT_INCOME), len(KAT_NERACA), len(KAT_EXPENSE),
            len(KAT_LAIN))
    for i in range(n):
        rows.append([
            KANTONG[i] if i < len(KANTONG) else "",
            KAT_INCOME[i] if i < len(KAT_INCOME) else "",
            KAT_NERACA[i] if i < len(KAT_NERACA) else "",
            KAT_EXPENSE[i] if i < len(KAT_EXPENSE) else "",
            KAT_LAIN[i] if i < len(KAT_LAIN) else "",
        ])
    put(ws, f"A{BARIS_HEADER}", rows)

    # Kolom F: satu daftar tunggal untuk dropdown TRANSAKSI. Dipisah dari lima
    # kolom di atas karena dropdown butuh rentang tanpa sel kosong; kolom B-E
    # panjangnya tidak sama, sehingga sel kosongnya akan muncul sebagai pilihan
    # kosong bila dipakai langsung sebagai rujukan validasi.
    kolom_dropdown = [["DAFTAR DROPDOWN KATEGORI"]]
    kolom_dropdown += [[k] for k in KAT_DROPDOWN]
    put(ws, f"{_col_letter(KOL_DROPDOWN)}{BARIS_HEADER}", kolom_dropdown)

    # Catatan diletakkan setelah tabel, bukan di baris mati, supaya tidak
    # tertimpa ketika daftar kategori bertambah.
    catatan_row = BARIS_HEADER + len(rows) + 1
    put(ws, f"A{catatan_row}",
        [["Kantong = kantong uang perusahaan: BRI, BNI, Jago, UANG KAS.\n"
          "UANG KAS = kas operasional (tunai). Antar-bank via FLIP tetap dicatat\n"
          "dari kantong asal + kategori Biaya-Administrasi Flip dan Bank untuk biayanya."]])


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
    # KAT_EXPENSE hanya berisi beban sungguhan, jadi tidak perlu pengecualian.
    for i, k in enumerate(KAT_EXPENSE):
        exp.append([f"=SETUP!D{4 + i}",
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
            [f"=SETUP!D{4 + KAT_EXPENSE.index(k)}"]
            + [f'=SUMIFS(TRANSAKSI!D:D,TRANSAKSI!E:E,$A{r},'
               f'TRANSAKSI!A:A,">="&{c}$3,TRANSAKSI!A:A,"<="&EOMONTH({c}$3,0))'
               for c in MONTH_COLS]
            + [f"=SUM(B{r}:M{r})"])
    rows.append(["TOTAL PENGELUARAN"]
                + [f"=SUM({c}6:{c}{EXP_TOTAL_ROW - 1})" for c in MONTH_COLS]
                + [f"=SUM(N6:N{EXP_TOTAL_ROW - 1})"])
    put(ws, "A6", rows)

    memo = EXP_TOTAL_ROW + 2
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
    # Nama kategori mengikuti cash_report/categories.py; jangan hardcode nama lama.
    T = EXP_TOTAL_ROW
    BB = EXP_ROW["Bahan Baku"]
    PJ = EXP_ROW["Biaya-Pajak"]
    BG = EXP_ROW["Biaya-Bunga Bank"]
    tpl = [
        ("PENDAPATAN", "='YEARLY OVERVIEW'!{c}6"),
        ("(-) HPP / Bahan Baku", f"='EXPENSE DETAIL'!{{c}}{BB}"),
        ("LABA KOTOR", "={c}5-{c}6"),
        ("(-) Beban Operasional",
         f"='EXPENSE DETAIL'!{{c}}{T}-'EXPENSE DETAIL'!{{c}}{BB}"
         f"-'EXPENSE DETAIL'!{{c}}{PJ}-'EXPENSE DETAIL'!{{c}}{BG}"),
        ("LABA SEBELUM PAJAK", "={c}7-{c}8"),
        ("(-) Pajak", f"='EXPENSE DETAIL'!{{c}}{PJ}"),
        ("(-) Biaya Bunga Bank", f"='EXPENSE DETAIL'!{{c}}{BG}"),
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
        # Dropdown kolom Kategori di TRANSAKSI, sumbernya daftar di SETUP.
        _validasi_dropdown(sheets["TRANSAKSI"].id),
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
