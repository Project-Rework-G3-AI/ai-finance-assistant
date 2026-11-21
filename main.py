"""Bot Pencatatan Transaksi — Milestone 1: Telegram bot -> ekstraksi bukti transaksi -> Cash Report (Google Sheets).

Satu proses: FastAPI (endpoint ekstraksi + serve) + long-poll Telegram (asyncio task).
Tanpa database. Gagal tulis ke Cash Report -> antre di pending.jsonl (retry otomatis).

Mode ekstraksi:
  - mock  (default, tanpa AI_API_KEY): tanggal dari nama file/caption, nominal dari caption.
  - vision (AI_API_KEY terisi): kirim gambar ke endpoint kompatibel OpenAI -> JSON field.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

import sentry_setup

load_dotenv(Path(__file__).parent / ".env")

# Logging dan Sentry dipasang sebelum apa pun yang bisa gagal, supaya error saat
# inisialisasi ikut terlaporkan.
sentry_setup.setup_logging()
SENTRY_AKTIF = sentry_setup.init_sentry()
log = logging.getLogger("bot")

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_ALLOWED = {int(x) for x in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if x.strip()}
SA_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json").strip()
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()  # folder Receipts (upload foto)
CR_FOLDER_ID = os.getenv("CASH_REPORT_FOLDER_ID", "").strip()
CR_TEMPLATE_ID = os.getenv("CASH_REPORT_TEMPLATE_ID", "").strip()
CR_DEFAULT_BANK = os.getenv("CR_DEFAULT_BANK", "TUNAI").strip().upper()
AI_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini").strip()

PENDING = Path(__file__).parent / "pending.jsonl"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

CATATAN_MOCK = "Mock ekstraksi: isi dari nama file/caption — periksa & koreksi sebelum dipakai."


# ---------- ekstraksi ----------

def _mock_extract(filename: str, caption: str) -> dict:
    """Ekstraksi tanpa AI: tanggal dari nama file, nominal/keterangan dari caption."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    tanggal = m.group(1) if m else datetime.now().strftime("%Y-%m-%d")
    nom = re.search(r"Rp\s*([\d.,]+)", caption, re.I)
    nominal = int(nom.group(1).replace(".", "").replace(",", "")) if nom else None
    arah = "masuk" if re.search(r"\b(masuk|penjualan|transfer dari)\b", caption, re.I) else "keluar"
    catatan = CATATAN_MOCK
    if not nominal:
        catatan += " Nominal tidak terbaca — isi manual."
    return {
        "tanggal": tanggal,
        "keterangan": caption.strip() or Path(filename).stem,
        "nominal": nominal,
        "arah": arah,
        "kategori": "",
        "catatan": catatan,
        "bank": "",
        "kantong_tujuan": "",
        "mode": "mock",
    }


def _gabung_keterangan(llm_ket: str, caption: str, filename: str) -> str:
    """Keterangan = hasil LLM; caption pengirim digabung dengan ' — ' bila berbeda."""
    llm = (llm_ket or "").strip()
    cap = (caption or "").strip()
    if llm and cap and llm.lower() != cap.lower():
        return f"{llm} — {cap}"
    return llm or cap or filename


async def _vision_extract(client: httpx.AsyncClient, filename: str, image_bytes: bytes, caption: str) -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    prompt = (
        "Ekstrak data transaksi dari bukti ini. Balas HANYA JSON tanpa teks lain: "
        '{"tanggal":"YYYY-MM-DD","keterangan":"...","nominal":number,'
        '"arah":"masuk|keluar|transfer",'
        '"kategori":"satu dari: Bahan Baku, Biaya-Gaji Karyawan, Biaya-Konsumsi, '
        'Biaya-Perlengkapan Kantor dan Administrasi, Biaya-Transportasi, Biaya-Ongkir, '
        'Biaya-Perbaikan Bangunan, Biaya-Operasional, Biaya-Pembelian Aset, Biaya-Sosial, '
        'Administrasi Bank, Pajak, Bunga, Admin Flip, Transfer Antar Bank, Penjualan, Lainnya",'
        '"bank":"kantong asal dana — salah satu dari: BRI, BNI, Jago, TUNAI; '
        'kosong bila tidak terbaca",'
        '"kantong_tujuan":"hanya bila arah=transfer — kantong tujuan: '
        'BRI, BNI, Jago, TUNAI; kosong bila bukan transfer"}'
    )
    if caption:
        prompt += f"\nCaption Telegram: {caption}"
    r = await client.post(
        f"{AI_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {AI_KEY}"},
        json={
            "model": AI_MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ]}],
            "temperature": 0,
        },
        timeout=90,
    )
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        # raise_for_status() hanya membawa kode status. Isi respons dari provider
        # (mis. {"error":{"message":...}}) menjelaskan penyebab sebenarnya, jadi
        # dilampirkan sebelum diteruskan.
        body = ""
        with suppress(Exception):
            body = e.response.text[:800]
        raise RuntimeError(
            f"AI HTTP {e.response.status_code} dari {AI_BASE}: {body or '(respons kosong)'}"
        ) from e
    text = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("balasan AI bukan JSON")
    data = json.loads(m.group(0))
    arah = str(data.get("arah", "")).lower()
    keterangan = _gabung_keterangan(str(data.get("keterangan") or ""), caption, filename)

    notes = []
    if not data.get("tanggal"):
        notes.append("tanggal tidak terbaca — pakai hari ini")
    if not data.get("nominal"):
        notes.append("nominal tidak terbaca — isi manual")
    if not str(data.get("bank") or "").strip():
        notes.append("kantong tidak terbaca — pakai default")
    if not str(data.get("kategori") or "").strip():
        notes.append("kategori tidak terbaca — isi manual")
    catatan = "Ekstraksi AI — wajib ditinjau sebelum dipakai."
    if notes:
        catatan += " (" + ", ".join(notes) + ")"

    return {
        "tanggal": str(data.get("tanggal") or datetime.now().strftime("%Y-%m-%d")),
        "keterangan": keterangan,
        "nominal": int(data["nominal"]) if data.get("nominal") else None,
        "arah": arah if arah in ("masuk", "keluar", "transfer") else "keluar",
        "kategori": str(data.get("kategori") or ""),
        "catatan": catatan,
        "bank": str(data.get("bank") or "").strip().upper(),
        "kantong_tujuan": str(data.get("kantong_tujuan") or "").strip().upper(),
        "mode": "vision",
    }


async def extract(client: httpx.AsyncClient, filename: str, image_bytes: bytes, caption: str) -> dict:
    if AI_KEY:
        try:
            return await _vision_extract(client, filename, image_bytes, caption)
        except Exception as e:  # fallback: alur tetap jalan saat AI gagal
            # Fallback ini menelan error, jadi tanpa capture_exception kegagalan
            # AI tidak pernah terlihat di Sentry.
            log.warning("Ekstraksi AI gagal, jatuh ke mock: %s: %s", type(e).__name__, e)
            sentry_setup.capture_exception(e)
            res = _mock_extract(filename, caption)
            res["catatan"] = f"AI gagal ({type(e).__name__}: {e}) — jatuh ke mock. {CATATAN_MOCK}"
            return res
    return _mock_extract(filename, caption)


# ---------- Google Drive (OAuth user) ----------
# Drive = OAuth akun user (SA tidak bisa membuat file: kuota SA = 0, error
# storageQuotaExceeded). Sel/struktur Cash Report = service account (folder
# sudah di-share ke SA). Scope penuh diperlukan: cari folder & copy template
# milik user — token lama ber-scopes drive.file harus dibuat ulang (README).

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
OAUTH_REFRESH_TOKEN = os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN", "").strip()


def _drive_ready() -> bool:
    return bool(DRIVE_FOLDER_ID and OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET and OAUTH_REFRESH_TOKEN)


def _oauth_creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = Credentials.from_authorized_user_info(
        {
            "refresh_token": OAUTH_REFRESH_TOKEN,
            "client_id": OAUTH_CLIENT_ID,
            "client_secret": OAUTH_CLIENT_SECRET,
        },
        scopes=[DRIVE_SCOPE],
    )
    creds.refresh(Request())
    return creds


_drive_svc = None


def _drive():
    global _drive_svc
    if _drive_svc is None:
        from googleapiclient.discovery import build
        _drive_svc = build("drive", "v3", credentials=_oauth_creds(), cache_discovery=False)
    return _drive_svc


_sheet_cli = None


def _sheets():
    global _sheet_cli
    if _sheet_cli is None:
        import gspread
        sa_raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        _sheet_cli = (
            gspread.service_account_from_dict(json.loads(sa_raw), scopes=GOOGLE_SCOPES)
            if sa_raw
            else gspread.service_account(filename=SA_FILE, scopes=GOOGLE_SCOPES)
        )
    return _sheet_cli


def upload_drive(image_bytes: bytes, filename: str) -> str:
    """Upload foto ke folder Drive (akun user via OAuth). Return webViewLink."""
    import io

    from googleapiclient.http import MediaIoBaseUpload

    drive = _drive()
    mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    f = drive.files().create(
        body={"name": filename, "parents": [DRIVE_FOLDER_ID]},
        media_body=MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype=mime),
        fields="id, webViewLink",
    ).execute()
    return f.get("webViewLink", "")


def _escape_drive_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_or_create_folder(folder_name: str, parent_id: str) -> str:
    """Folder di Drive (OAuth): cari, kalau tidak ada buat. Gagal jika >1."""
    q = (
        f"name = '{_escape_drive_query(folder_name)}' "
        f"and '{parent_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    files = _drive().files().list(q=q, fields="files(id, name)", pageSize=100).execute().get("files", [])
    if len(files) > 1:
        raise RuntimeError(f"Folder ganda ditemukan: {folder_name}")
    if files:
        return files[0]["id"]
    f = _drive().files().create(
        body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
        fields="id",
    ).execute()
    return f["id"]


def _find_or_create_spreadsheet(year: str, year_folder_id: str) -> dict:
    """Spreadsheet gabungan 'Cash Report {tahun}': cari, kalau tidak ada copy template."""
    name = f"Cash Report {year}"
    q = (
        f"name = '{_escape_drive_query(name)}' "
        f"and '{year_folder_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.spreadsheet' "
        "and trashed = false"
    )
    files = _drive().files().list(q=q, fields="files(id, name, webViewLink)", pageSize=100).execute().get("files", [])
    if len(files) > 1:
        raise RuntimeError(f"Cash Report ganda ditemukan: {name}")
    if files:
        return files[0]
    if not CR_TEMPLATE_ID:
        raise RuntimeError("CASH_REPORT_TEMPLATE_ID kosong")
    f = _drive().files().copy(
        fileId=CR_TEMPLATE_ID,
        body={"name": name, "parents": [year_folder_id]},
        fields="id, name, webViewLink",
    ).execute()
    _init_year_dates(f["id"], year)
    return f


def _init_year_dates(spreadsheet_id: str, year: str) -> None:
    """Setelah copy template: sel periode RECAP = 1 Januari tahun berjalan.

    Sheet RECAP/YEARLY/EXPENSE/INCOME semuanya turunan dari sel ini, jadi
    cukup satu tulisan.

    Formula di bawah memakai koma sebagai pemisah argumen, jadi locale harus
    dipaksa en_US lebih dulu. Berkas hasil copy mewarisi locale template; bila
    locale-nya Indonesia (in_ID), Google Sheets membaca formula berkoma sebagai
    parse error dan sel jadi #ERROR!.
    """
    sh = _open_spreadsheet(spreadsheet_id)
    sh.update_locale("en_US")
    sh.worksheet("RECAP OVERVIEW").update(
        values=[[f"=DATE({year},1,1)"]],
        range_name="B3",
        value_input_option="USER_ENTERED",
    )


_ss_cache: dict = {}


def _open_spreadsheet(spreadsheet_id: str):
    if spreadsheet_id not in _ss_cache:
        _ss_cache[spreadsheet_id] = _sheets().open_by_key(spreadsheet_id)
    return _ss_cache[spreadsheet_id]


def _safe(v) -> str:
    """Cegah teks user/AI diinterpretasi sebagai formula (USER_ENTERED)."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def write_cash_report(rec: dict, image_bytes: bytes = b"", filename: str = "") -> dict:
    """Tulis transaksi ke ledger 'Cash Report {tahun}', sheet TRANSAKSI.

    Flat ledger: append di baris pertama kolom A kosong. Transfer antar kantong
    ditulis 2 baris berpasangan — keduanya berbagi Ref ID di kolom I (pasangan
    dikenali dari Ref ID yang sama muncul di2 baris).
    Return {"status": "ok"|"dup", "worksheet", "row", "link"}.
    Urutan: dedupe dulu (Ref ID kolom I), baru upload foto & tulis baris.
    """
    if not CR_FOLDER_ID or not CR_TEMPLATE_ID:
        raise RuntimeError("CASH_REPORT_FOLDER_ID / CASH_REPORT_TEMPLATE_ID belum diisi")
    tanggal = str(rec.get("tanggal") or datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d"))
    year = tanggal[:4]
    kantong = str(rec.get("bank") or "").strip().upper() or CR_DEFAULT_BANK

    year_folder = _find_or_create_folder(year, CR_FOLDER_ID)
    ss_file = _find_or_create_spreadsheet(year, year_folder)
    sh = _open_spreadsheet(ss_file["id"])
    try:
        ws = sh.worksheet("TRANSAKSI")
    except Exception as e:
        raise FileNotFoundError("Sheet TRANSAKSI tidak ditemukan — periksa CASH_REPORT_TEMPLATE_ID") from e

    if rec["ref_id"] in ws.col_values(9):  # kolom I = Ref ID
        return {"status": "dup", "worksheet": ws.title, "row": 0, "link": ""}

    link = ""
    if _drive_ready() and image_bytes:
        try:
            link = upload_drive(image_bytes, filename or rec.get("sumber_file") or "receipt.jpg")
        except Exception as e:
            # baris tetap tersimpan; kolom Link Bukti kosong
            log.warning("Upload Drive gagal, link bukti dikosongkan: %s: %s", type(e).__name__, e)
            sentry_setup.capture_exception(e)

    col_a = ws.col_values(1)
    row = next((i + 1 for i, v in enumerate(col_a) if not str(v).strip()), len(col_a) + 1)

    nominal = rec.get("nominal") or 0
    arah = rec.get("arah")
    kantong_tujuan = str(rec.get("kantong_tujuan") or "").strip().upper()
    is_pair = bool(arah == "transfer" and kantong_tujuan and kantong_tujuan != kantong)
    masuk = arah == "masuk"
    catatan = rec.get("catatan") or ""
    if arah == "transfer" and not is_pair:
        catatan += " [transfer tanpa kantong tujuan terbaca — diperlakukan sebagai keluar]"

    def _baris(k_: str, keluar, masuk_nilai) -> list:
        return [
            tanggal, k_, masuk_nilai, keluar,
            _safe(rec.get("kategori")), _safe(rec.get("keterangan")),
            "draft", _safe(catatan), rec["ref_id"],
            _safe(rec.get("sumber_file")), link,
        ]

    if is_pair:
        values = [
            _baris(kantong, nominal, ""),
            _baris(kantong_tujuan, "", nominal),
        ]
    else:
        values = [_baris(kantong, "" if masuk else nominal, nominal if masuk else "")]
    ws.update(
        values=values,
        range_name=f"A{row}:K{row + len(values) - 1}",
        value_input_option="USER_ENTERED",
    )
    return {"status": "ok", "worksheet": ws.title, "row": row, "link": link}


def push_pending(rec: dict, error: str) -> None:
    with PENDING.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**rec, "_error": error, "_ts": int(time.time())}, ensure_ascii=False) + "\n")


def flush_pending(client: httpx.AsyncClient) -> int:
    """Kirim ulang antrean. Return jumlah yang masih tersisa.

    Baris dibaca satu per satu dan dikumpulkan dulu, baru file ditulis ulang.
    Versi sebelumnya menghapus file sebelum memproses, sehingga satu baris JSON
    rusak membuat seluruh antrean transaksi hilang tanpa bisa dipulihkan.
    """
    if not PENDING.exists():
        return 0
    lines = PENDING.read_text(encoding="utf-8").strip().splitlines()
    sisa = []
    for ln in lines:
        if not ln.strip():
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError as e:
            # Baris rusak disimpan apa adanya agar tidak hilang. WARNING +
            # capture: satu event berisi traceback, tanpa dobel lewat
            # LoggingIntegration (yang hanya bereaksi pada level ERROR).
            log.warning("Baris antrean tidak bisa dibaca sebagai JSON: %s", e)
            sentry_setup.capture_exception(e)
            sisa.append(ln)
            continue
        rec.pop("_error", None)
        rec.pop("_ts", None)
        try:
            write_cash_report(rec)  # tanpa gambar: retry hanya barisnya, link kosong
        except Exception as e:
            # Retry gagal berarti transaksi belum tercatat; ini perlu terlihat.
            log.warning("Retry antrean gagal, dikembalikan ke pending: %s: %s", type(e).__name__, e)
            sentry_setup.capture_exception(e)
            # Simpan dengan anotasi error; ditulis sekali di akhir, bukan
            # append per baris, agar isi file tidak tercampur dua sumber.
            sisa.append(json.dumps({**rec, "_error": f"retry gagal: {e}", "_ts": int(time.time())},
                                   ensure_ascii=False))

    # Tulis ulang hanya bila masih ada sisa; file kosong dihapus agar /health
    # melaporkan pending=false dengan benar.
    if sisa:
        PENDING.write_text("\n".join(sisa) + "\n", encoding="utf-8")
    else:
        PENDING.unlink(missing_ok=True)
    return len(sisa)


# ---------- Telegram ----------

TG_API = "https://api.telegram.org/bot{token}/{method}"


async def tg_call(client: httpx.AsyncClient, method: str, **payload) -> dict:
    r = await client.post(TG_API.format(token=TG_TOKEN, method=method), json=payload, timeout=90)
    data = r.json()
    if not data.get("ok"):
        # Sertakan kode error asli Telegram (bukan hanya description) supaya
        # kasus seperti 429 rate limit atau 403 bot diblokir bisa dibedakan.
        raise RuntimeError(
            f"Telegram {method} gagal: error_code={data.get('error_code')} "
            f"description={data.get('description')!r}"
        )
    return data["result"]


async def tg_send(client: httpx.AsyncClient, chat_id: int, text: str) -> None:
    """Kirim pesan Telegram; kegagalan tidak boleh menghentikan alur.

    Sebelumnya memakai suppress(Exception) tanpa jejak. Akibatnya kasus nyata
    seperti bot diblokir user atau 429 rate limit hilang tanpa bekas, padahal
    user tidak menerima balasan apa pun. Sekarang kegagalan tetap dicatat.
    """
    try:
        await tg_call(client, "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as e:
        # WARNING + capture: pesan gagal terkirim bukan kegagalan fatal, tapi
        # perlu terlihat karena user tidak menerima notifikasi apa pun.
        log.warning("Kirim pesan Telegram gagal (chat %s): %s: %s", chat_id, type(e).__name__, e)
        sentry_setup.capture_exception(e)


async def handle_update(client: httpx.AsyncClient, upd: dict) -> None:
    msg = upd.get("message") or upd.get("channel_post")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    if TG_ALLOWED and chat_id not in TG_ALLOWED:
        await tg_send(client, chat_id, "Chat ini tidak terdaftar. Minta akses ke admin.")
        return

    doc = msg.get("document")
    photo = msg.get("photo")
    if not doc and not photo:
        await tg_send(client, chat_id, "Kirim foto/screenshot bukti transaksi (bisa pakai caption, mis. <i>Rp195.000 penjualan satvika</i>).")
        return

    if photo:
        fid = photo[-1]["file_id"]
        filename = f"photo_{msg.get('date', int(time.time()))}.jpg"
    else:
        mime = (doc.get("mime_image") or doc.get("mime_type") or "")
        if not mime.startswith("image/"):
            await tg_send(client, chat_id, "File bukan gambar. Kirim JPG/PNG bukti transaksi.")
            return
        fid = doc["file_id"]
        filename = doc.get("file_name") or f"doc_{msg.get('date', int(time.time()))}"

    caption = msg.get("caption") or ""
    info = await tg_call(client, "getFile", file_id=fid)
    url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{info['file_path']}"
    img = await client.get(url, timeout=90)
    img.raise_for_status()

    rec = await extract(client, filename, img.content, caption)
    rec = {**rec, "sumber_file": filename, "ref_id": f"tg:{fid}"}
    try:
        hasil = await asyncio.to_thread(write_cash_report, rec, img.content, filename)
    except Exception as e:
        # log.exception() level ERROR sudah dikirim sebagai event oleh
        # LoggingIntegration, jadi tidak perlu capture_exception() lagi.
        log.exception("Tulis Cash Report gagal, masuk antrean")
        push_pending(rec, str(e))
        await tg_send(client, chat_id, f"⚠️ Ekstraksi OK, tapi tulis ke Cash Report gagal ({type(e).__name__}). Masuk antrean, dikirim ulang otomatis.")
        return
    if hasil["status"] == "dup":
        await tg_send(client, chat_id, "♻️ Sudah pernah dicatat — dilewati.")
        return
    nominal = f"Rp{rec['nominal']:,}" if rec["nominal"] else "<i>belum terbaca</i>"
    kantong = rec.get("bank") or CR_DEFAULT_BANK
    tujuan = rec.get("kantong_tujuan") or ""
    arah_teks = f"transfer {kantong}→{tujuan}" if rec["arah"] == "transfer" and tujuan else rec["arah"]
    baris_bukti = f'\n<a href="{hasil["link"]}">Bukti transfer</a>' if hasil["link"] else ""
    await tg_send(
        client, chat_id,
        f"✅ Draft tercatat — {hasil['worksheet']} baris {hasil['row']}\n"
        f"{rec['tanggal']} · {nominal} · {arah_teks}\n"
        f"Keterangan: {rec['keterangan']}{baris_bukti}\n"
        f"Status: <b>draft</b> — periksa & ubah ke verified di Sheet.",
    )


async def poll_loop() -> None:
    offset = 0
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # retry antrean lokal setiap siklus
                if PENDING.exists():
                    flush_pending(client)
                updates = await tg_call(client, "getUpdates", offset=offset, timeout=25, allowed_updates=["message", "channel_post"])
                for upd in updates:
                    offset = upd["update_id"] + 1
                    try:
                        await handle_update(client, upd)
                    except Exception as e:
                        # Satu update gagal tidak boleh menghentikan loop, tapi
                        # kegagalannya tetap harus terlihat di Sentry.
                        # log.exception() level ERROR sudah dikirim sebagai event
                        # oleh LoggingIntegration, jadi tidak perlu capture lagi.
                        log.exception("Gagal memproses update Telegram")
                        chat = (upd.get("message") or {}).get("chat", {}).get("id")
                        if chat:
                            await tg_send(client, chat, f"❌ Gagal memproses: {type(e).__name__}: {e}")
            except Exception:
                # Loop terluar: menelan semua error agar bot tetap hidup. Tanpa
                # laporan di sini, bot bisa diam berjam-jam tanpa jejak apa pun.
                log.exception("poll_loop gagal, ulang dalam 3 detik")
                await asyncio.sleep(3)


# ---------- API & server ----------

class ExtractReq(BaseModel):
    filename: str
    image_base64: str | None = None
    caption: str = ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = None
    if TG_TOKEN and TG_ALLOWED:
        task = asyncio.create_task(poll_loop())
        log.info("Bot Telegram aktif, long polling dimulai")
    else:
        log.warning("Telegram nonaktif: isi TELEGRAM_BOT_TOKEN & TELEGRAM_ALLOWED_CHAT_IDS di .env")
    yield
    if task:
        task.cancel()


app = FastAPI(title="Transaction Recording Bot - Milestone 1", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "ok": True,
        "telegram": bool(TG_TOKEN and TG_ALLOWED),
        "sheets": bool(CR_FOLDER_ID and CR_TEMPLATE_ID),
        "ai": "vision" if AI_KEY else "mock",
        "drive": _drive_ready(),
        "pending": PENDING.exists(),
        "sentry": SENTRY_AKTIF,
    }


@app.post("/api/extract")
async def api_extract(req: ExtractReq):
    async with httpx.AsyncClient() as client:
        raw = base64.b64decode(req.image_base64) if req.image_base64 else b""
        rec = await extract(client, req.filename, raw, req.caption)
        ref = "manual:" + re.sub(r"\W+", "-", req.filename)[:80]
        rec = {**rec, "sumber_file": req.filename, "ref_id": ref}
        try:
            hasil = await asyncio.to_thread(write_cash_report, rec, raw, req.filename)
        except Exception as e:
            # log.exception() level ERROR sudah dikirim sebagai event oleh
            # LoggingIntegration, jadi tidak perlu capture_exception() lagi.
            log.exception("Tulis Cash Report gagal via API, masuk antrean")
            push_pending(rec, str(e))
            return {**rec, "sheet": "pending", "error": str(e)}
        return {**rec, "sheet": hasil["status"], "worksheet": hasil["worksheet"],
                "row": hasil["row"], "link_bukti": hasil["link"]}


if __name__ == "__main__":
    import uvicorn
    # HOST=0.0.0.0 untuk hosting (Render dkk); default tetap lokal agar tidak terekspos
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
