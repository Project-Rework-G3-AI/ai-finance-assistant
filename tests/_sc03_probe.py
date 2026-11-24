"""Harness pengukuran SC-03: memanggil rantai asli, mengukur tiap tahap.

Yang dipanggil adalah fungsi produksi apa adanya:

    main.extract()           -> panggilan model sungguhan
    main.write_cash_report() -> dedupe + upload Drive + append Sheets

Pembagian tahap dilakukan dengan membungkus fungsi internal, bukan menebak:

- `extract` = waktu `main.extract()`
- `upload`  = waktu `main.upload_drive()`, yang dipanggil dari dalam
              `write_cash_report`
- `dedupe`  = sisa waktu `write_cash_report` sebelum tulis baris
- `append`  = waktu `ws.update()` saat menulis baris
- `reply`   = waktu menyusun dan mengirim permintaan balasan

Yang di-mock hanya dua hal, dan alasannya:

1. **Telegram.** Tidak ada bot token di mesin ini, dan mengirim pesan sungguhan
   ke chat orang lain bukan bagian dari pengukuran.

2. **Lokasi penyimpanan.** Diarahkan ke folder SANDBOX, bukan folder perusahaan,
   supaya data keuangan riil tidak tercemar baris uji.

Kredensial tidak pernah dicetak.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Modul kredensial Google. Bisa diarahkan lewat env bila lokasinya berbeda.
_GOOGLE_SCRIPTS = os.getenv("GOOGLE_SCRIPTS_DIR", "").strip()
if _GOOGLE_SCRIPTS:
    sys.path.insert(0, _GOOGLE_SCRIPTS)

# Sandbox wajib diisi lewat environment: pengukuran menulis baris sungguhan, dan
# menulis ke folder perusahaan akan mencemari data keuangan riil. Tidak ada nilai
# bawaan supaya salah arah tidak mungkin terjadi tanpa disadari.
SANDBOX_FOLDER = os.getenv("SC03_SANDBOX_FOLDER", "").strip()
SANDBOX_TEMPLATE = os.getenv("SC03_SANDBOX_TEMPLATE", "").strip()


def siapkan_env() -> None:
    """Arahkan aplikasi ke sandbox dan pasang kredensial model."""
    if not SANDBOX_FOLDER or not SANDBOX_TEMPLATE:
        raise SystemExit(
            "SC03_SANDBOX_FOLDER dan SC03_SANDBOX_TEMPLATE wajib diisi.\n"
            "Pengukuran menulis baris sungguhan; arahkan ke folder sandbox, "
            "bukan folder Cash Report perusahaan."
        )
    os.environ["CASH_REPORT_FOLDER_ID"] = SANDBOX_FOLDER
    os.environ["CASH_REPORT_TEMPLATE_ID"] = SANDBOX_TEMPLATE
    os.environ.setdefault("CR_DEFAULT_BANK", "BNI")

    # Kunci model dibaca dari .env repo sendiri lewat main.load_dotenv. Kalau
    # kosong, berhenti dengan pesan jelas alih-alih memanggil API tanpa kunci.
    if not os.getenv("AI_API_KEY"):
        raise SystemExit(
            "AI_API_KEY kosong. Isi .env lebih dulu (lihat .env.example)."
        )


def siapkan_klien(main) -> None:
    """Ganti klien Drive dan Sheets ke OAuth user.

    Produksi memakai service account untuk Sheets dan refresh token sendiri
    untuk Drive. Di mesin ini keduanya tidak ada, tetapi OAuth Hermes punya
    scope drive dan spreadsheets penuh, jadi dipakai untuk keduanya.
    """
    from google_api import get_credentials
    import gspread
    from googleapiclient.discovery import build as gbuild

    def _sheets_oauth():
        return gspread.authorize(get_credentials())

    def _drive_oauth():
        return gbuild("drive", "v3", credentials=get_credentials(), cache_discovery=False)

    main._sheets = _sheets_oauth
    main._sheet_cli = _sheets_oauth()
    main._drive = _drive_oauth
    main._drive_svc = _drive_oauth()


def pasang_pengukur(main, sample) -> dict:
    """Bungkus fungsi internal supaya tiap tahap terukur terpisah.

    Mengembalikan catatan asli agar bisa dipulihkan setelah selesai.
    """
    catatan = {}

    # --- upload Drive
    asli_upload = main.upload_drive
    catatan["upload_drive"] = asli_upload

    def upload_terukur(*a, **kw):
        t0 = time.perf_counter()
        try:
            return asli_upload(*a, **kw)
        finally:
            sample.stages["upload"] = sample.stages.get("upload", 0.0) + (time.perf_counter() - t0)

    main.upload_drive = upload_terukur

    # --- append Sheets: bungkus gspread worksheet.update lewat open_by_key
    asli_open = main._open_spreadsheet
    catatan["_open_spreadsheet"] = asli_open

    def open_terukur(*a, **kw):
        sh = asli_open(*a, **kw)
        asli_ws = sh.worksheet

        def worksheet_terukur(title):
            ws = asli_ws(title)
            asli_update = ws.update

            def update_terukur(*ua, **ukw):
                t0 = time.perf_counter()
                try:
                    return asli_update(*ua, **ukw)
                finally:
                    sample.stages["append"] = sample.stages.get("append", 0.0) + (
                        time.perf_counter() - t0)

            ws.update = update_terukur
            return ws

        sh.worksheet = worksheet_terukur
        return sh

    main._open_spreadsheet = open_terukur
    return catatan


def pulihkan(main, catatan: dict) -> None:
    for nama, fungsi in catatan.items():
        setattr(main, nama, fungsi)


async def ukur_satu(main, client, nama: str, gambar: bytes):
    """Ukur satu gambar melalui rantai produksi."""
    from sc03_latency import Sample

    sample = Sample(file=nama)
    catatan = pasang_pengukur(main, sample)

    try:
        t_awal = time.perf_counter()

        t0 = time.perf_counter()
        rec = await main.extract(client, nama, gambar, "")
        sample.stages["extract"] = time.perf_counter() - t0

        rec = {**rec, "sumber_file": nama, "ref_id": f"sc03:{nama}"}

        # write_cash_report menjalankan dedupe -> upload -> append. Waktu
        # upload dan append direkam oleh pembungkus di atas; sisanya adalah
        # dedupe (baca kolom Ref ID dan cari/buat folder serta spreadsheet).
        t0 = time.perf_counter()
        hasil = await asyncio.to_thread(main.write_cash_report, rec, gambar, nama)
        total_tulis = time.perf_counter() - t0

        terpakai = sample.stages.get("upload", 0.0) + sample.stages.get("append", 0.0)
        sample.stages["dedupe"] = max(0.0, total_tulis - terpakai)

        # Tahap reply: waktu menyusun dan mengirim permintaan balasan.
        t0 = time.perf_counter()
        await main.tg_send(client, 0, f"tersimpan di baris {hasil.get('row')}")
        sample.stages["reply"] = time.perf_counter() - t0

        sample.ok = True
        sample.status = hasil.get("status", "")
        sample.row = hasil.get("row", 0)
    except Exception as e:
        sample.ok = False
        sample.error = f"{type(e).__name__}: {e}"
    finally:
        pulihkan(main, catatan)

    return sample
