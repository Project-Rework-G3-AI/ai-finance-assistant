"""Verifikasi setup Drive & template Cash Report untuk main.py.

Jalankan: .venv/bin/python cash_report/verify_setup.py
Butuh CASH_REPORT_FOLDER_ID & CASH_REPORT_TEMPLATE_ID di .env.
"""

from dotenv import load_dotenv

load_dotenv()

import os

import gspread

MONTHS = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def main():
    tpl = os.getenv("CASH_REPORT_TEMPLATE_ID", "").strip()
    if not tpl:
        raise SystemExit("CASH_REPORT_FOLDER_ID & CASH_REPORT_TEMPLATE_ID belum diisi di .env")

    gc = gspread.service_account(
        filename=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    )

    try:
        sh = gc.open_by_key(tpl)
        print("1. SA bisa buka template        : OK (share folder ke SA benar)")
    except Exception as e:
        raise SystemExit(
            "1. SA TIDAK bisa buka template — share folder 'Cash Report' "
            f"ke client_email (Editor) dulu.\n   {e}"
        )

    titles = [w.title for w in sh.worksheets()]
    print("2. Tab:", titles)

    missing = [f"{m} 2025" for m in MONTHS if f"Cash Report - {m} 2025" not in titles]
    print("3. Tab bulan hilang/salah nama  :", missing or "tidak ada — 12 lengkap")
    print("4. Ada tab Config               :", any(t.strip().lower() == "config" for t in titles))

    w = next((x for x in sh.worksheets() if "config" not in x.title.lower()), sh.worksheets()[0])
    vals = w.col_values(2)
    sub = next((i + 1 for i, v in enumerate(vals) if v.strip().lower() == "sub total"), None)
    print(f"5. '{w.title}' — Sub Total baris :", sub or "TIDAK DITEMUKAN")
    print("6. B3 (header tahun)            :", repr(w.cell(3, 2).value))
    if sub:
        print("7. Formula E/F/G/H di Sub Total:", [w.cell(sub, c).value for c in (5, 6, 7, 8)])
    for r in (5, 6, 7):
        print(f"8. baris {r} A..P               :", w.row_values(r))


if __name__ == "__main__":
    main()
