"""Cara A: arahkan data 2026 ke file baru hasil template baru.

SKEMA TETAP: script ini mengasumsikan kolom TRANSAKSI A–K (indeks Masuk=2,
Keluar=3, Kategori=4, Link Bukti=10). Bila format template berubah, sesuaikan
indeks/range di bawah dulu. Baca selalu3 render (FORMATTED/UNFORMATTED/
FORMULA): jangan salin nilai terformat "Rp40,400" sebagai teks — SUMIFS jadi0.

Urutan pakai (setelah PR#15 merge):
  1. --rename-template   # rename template lama (syarat build ulang)
  2. build_template.py   # template baru -> catat id
  3. update CASH_REPORT_TEMPLATE_ID (.env lokal + dashboard Render) -> deploy
  4. --rename            # rename file data 2026 lama
  5. --pindah            # buat file baru dari template + pindah baris + verifikasi

Baris lama dinormalisasi kategorinya (KAT.normalize) saat pindah, jadi
'Penjualan' ikut menjadi nama baru. ACCOUNT saldo awal disalin bila terisi.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import main
from cash_report import categories as KAT

NAMA = "2026"


def _folder():
    return main._find_or_create_folder(NAMA, main.CR_FOLDER_ID)


def _file(nama):
    files = main._drive().files().list(
        q=f"name = '{nama}' and '{_folder()}' in parents and trashed = false",
        fields="files(id, name)", pageSize=5,
    ).execute().get("files", [])
    return files[0] if files else None


def cmd_rename():
    f = _file(f"Cash Report {NAMA}")
    if not f:
        print(f"Tidak ada Cash Report {NAMA} — tidak perlu rename.")
        return
    main._drive().files().update(
        fileId=f["id"], body={"name": f"Cash Report {NAMA} (lama)"}).execute()
    print(f"Renamed: {f['id']} -> Cash Report {NAMA} (lama)")


def cmd_rename_template():
    folder_t = main._find_or_create_folder("TEMPLATE", main.CR_FOLDER_ID)
    files = main._drive().files().list(
        q=f"name = 'Cash Report TEMPLATE' and '{folder_t}' in parents and trashed = false",
        fields="files(id, name)", pageSize=5,
    ).execute().get("files", [])
    if not files:
        print("Template 'Cash Report TEMPLATE' tidak ada — tidak perlu rename.")
        return
    main._drive().files().update(
        fileId=files[0]["id"], body={"name": "Cash Report TEMPLATE (lama)"}).execute()
    print(f"Template lama renamed: {files[0]['id']} -> Cash Report TEMPLATE (lama)")


def cmd_pindah():
    lama = _file(f"Cash Report {NAMA} (lama)")
    if not lama:
        print("File lama (lama) tidak ditemukan — jalankan --rename dulu.")
        return
    # buat file baru dari template baru (nama kosong -> bot copy template)
    baru = main._find_or_create_spreadsheet(NAMA, _folder())
    main._init_year_dates(baru["id"], NAMA)
    print(f"File baru: {baru['id']} ({baru.get('url', '')})")

    sh_lama = main._sheets().open_by_key(lama["id"])
    ws_lama = sh_lama.worksheet("TRANSAKSI")
    # Baca3 render sekaligus: nilai mentah untuk kolom numerik (jangan salin
    # "Rp40,400" sebagai teks — SUMIFS jadi0), tampilan untuk tanggal/teks,
    # FORMULA untuk Link Bukti (=HYPERLINK).
    fmt = ws_lama.get("A2:K", value_render_option="FORMATTED_VALUE") or []
    raw = ws_lama.get("A2:K", value_render_option="UNFORMATTED_VALUE") or []
    fml = ws_lama.get("A2:K", value_render_option="FORMULA") or []
    data = []
    for i, rf in enumerate(fmt):
        if not (rf and str(rf[0]).strip()):
            continue
        rf = (rf + [""] * 11)[:11]
        rr = ((raw[i] if i < len(raw) else []) + [""] * 11)[:11]
        rl = ((fml[i] if i < len(fml) else []) + [""] * 11)[:11]
        baris = list(rf)
        for idx in (2, 3):                      # Masuk / Keluar: angka mentah
            baris[idx] = "" if rr[idx] is None else rr[idx]
        baris[10] = rl[10]                      # Link Bukti: pertahankan formula
        # normalisasi kategori (kolom E, indeks 4) ke nama baru
        k = str(baris[4]).strip()
        if k:
            norm = KAT.normalize(k)
            if norm != k:
                print(f"  kategori: {k!r} -> {norm!r}")
                baris[4] = norm
        data.append(baris)
    print(f"baris data lama: {len(data)}")

    sh_baru = main._sheets().open_by_key(baru["id"])
    ws = sh_baru.worksheet("TRANSAKSI")
    col_a = ws.col_values(1)
    mulai = next((i + 1 for i, v in enumerate(col_a) if not str(v).strip()), len(col_a) + 1)
    if data:
        ws.update(values=data, range_name=f"A{mulai}:K{mulai + len(data) - 1}",
                  value_input_option="USER_ENTERED")
    print(f"ditulis di baris {mulai}..{mulai + len(data) - 1}")

    # saldo awal ACCOUNT (baris data manual) disalin bila terisi — angka mentah
    acc_lama = sh_lama.worksheet("ACCOUNT").get("A4:E", value_render_option="UNFORMATTED_VALUE") or []
    acc_baru = sh_baru.worksheet("ACCOUNT")
    ub = []
    for i, r in enumerate(acc_lama, start=4):
        sal = r[4] if len(r) > 4 else ""        # kolom E = Saldo Awal
        kantong = str(r[0]).strip() if r else ""
        if kantong and sal not in ("", None):
            ub.append([i, kantong, sal])
    if ub:
        print("saldo awal terisi (kolom E ACCOUNT lama):", ub)
        for i, kantong, sal in ub:
            acc_baru.update(values=[[sal]], range_name=f"E{i}",
                            value_input_option="USER_ENTERED")
    else:
        print("saldo awal ACCOUNT lama kosong — tidak disalin.")

    # verifikasi: hitung ulang RECAP vs isi ledger baru (angka mentah)
    import time
    time.sleep(3)
    vals = ws.get("A2:K", value_render_option="UNFORMATTED_VALUE") or []
    vals = [r for r in vals if r and str(r[0]).strip()]

    def num(v):
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).replace("Rp", "").replace(",", "").strip()
        try:
            return float(s)
        except ValueError:
            return 0.0

    pend = sum(num(r[2]) for r in vals if len(r) > 4 and r[4] != "Transfer Antar Bank")
    peng = sum(num(r[3]) for r in vals if len(r) > 4 and r[4] != "Transfer Antar Bank")
    recap = sh_baru.worksheet("RECAP OVERVIEW")
    rp = recap.cell(6, 3, value_render_option="UNFORMATTED_VALUE").value or 0
    rg = recap.cell(7, 3, value_render_option="UNFORMATTED_VALUE").value or 0
    print(f"RECAP pend/peng = {rp}/{rg} | ledger = {pend}/{peng}")
    assert abs(rp - pend) < 1 and abs(rg - peng) < 1, "RECAP tidak cocok!"
    print("MIGRASI SELESAI — RECAP konsisten.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--rename", action="store_true", help="rename file data 2026")
    p.add_argument("--rename-template", action="store_true",
                   help="rename template lama (syarat build ulang)")
    p.add_argument("--pindah", action="store_true")
    a = p.parse_args()
    if a.rename:
        cmd_rename()
    elif a.rename_template:
        cmd_rename_template()
    elif a.pindah:
        cmd_pindah()
    else:
        p.print_help()
