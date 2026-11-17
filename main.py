"""Bot Pencatatan Transaksi — Milestone 1: Telegram bot -> ekstraksi bukti transaksi -> Google Sheets.

Satu proses: FastAPI (endpoint ekstraksi + serve) + long-poll Telegram (asyncio task).
Tanpa database. Gagal kirim ke Sheets -> antre di pending.jsonl (retry otomatis).

Mode ekstraksi:
  - mock  (default, tanpa AI_API_KEY): tanggal dari nama file/caption, nominal dari caption.
  - vision (AI_API_KEY terisi): kirim gambar ke endpoint kompatibel OpenAI -> JSON field.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env")

TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_ALLOWED = {int(x) for x in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if x.strip()}
SHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "").strip()
SA_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json").strip()
DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
AI_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini").strip()

PENDING = Path(__file__).parent / "pending.jsonl"
HEADERS = ["Tanggal", "Keterangan", "Nominal", "Arah", "Kategori", "Status", "Sumber File", "Ref ID", "Confidence", "Tanggal Input", "Catatan", "Caption", "Link Bukti"]
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
    return {
        "tanggal": tanggal,
        "keterangan": caption.strip() or Path(filename).stem,
        "nominal": nominal,
        "arah": arah,
        "kategori": "",
        "confidence": 0.0,
        "catatan": CATATAN_MOCK,
        "caption": caption.strip(),
        "mode": "mock",
    }


async def _vision_extract(client: httpx.AsyncClient, filename: str, image_bytes: bytes, caption: str) -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    prompt = (
        "Ekstrak data transaksi dari bukti ini. Balas HANYA JSON tanpa teks lain: "
        '{"tanggal":"YYYY-MM-DD","keterangan":"...","nominal":number,'
        '"arah":"masuk|keluar","kategori":"satu dari: Bahan Baku, Biaya-Gaji Karyawan, '
        'Biaya-Konsumsi, Biaya-Perlengkapan Kantor dan Administrasi, Biaya-Transportasi, '
        'Biaya-Ongkir, Biaya-Perbaikan Bangunan, Biaya-Operasional, Biaya-Pembelian Aset, '
        'Biaya-Sosial, Penjualan, Lainnya"}'
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
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("balasan AI bukan JSON")
    data = json.loads(m.group(0))
    return {
        "tanggal": str(data.get("tanggal") or datetime.now().strftime("%Y-%m-%d")),
        "keterangan": str(data.get("keterangan") or caption or filename),
        "nominal": int(data["nominal"]) if data.get("nominal") else None,
        "arah": "masuk" if str(data.get("arah", "")).lower() == "masuk" else "keluar",
        "kategori": str(data.get("kategori") or ""),
        "confidence": 1.0,
        "catatan": "Ekstraksi AI — wajib ditinjau sebelum dipakai.",
        "caption": caption.strip(),
        "mode": "vision",
    }


async def extract(client: httpx.AsyncClient, filename: str, image_bytes: bytes, caption: str) -> dict:
    if AI_KEY:
        try:
            return await _vision_extract(client, filename, image_bytes, caption)
        except Exception as e:  # fallback: alur tetap jalan saat AI gagal
            res = _mock_extract(filename, caption)
            res["catatan"] = f"AI gagal ({type(e).__name__}: {e}) — jatuh ke mock. {CATATAN_MOCK}"
            return res
    return _mock_extract(filename, caption)


# ---------- Google Drive (arsip bukti transfer, OAuth user) ----------
# Service account tidak bisa: Google memblokir SA membuat file (kuota SA = 0,
# error storageQuotaExceeded) kecuali Shared Drive. Pakai OAuth akun user.

DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
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


def upload_drive(image_bytes: bytes, filename: str) -> str:
    """Upload foto ke folder Drive (akun user via OAuth). Return webViewLink."""
    import io

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    drive = build("drive", "v3", credentials=_oauth_creds(), cache_discovery=False)
    mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    f = drive.files().create(
        body={"name": filename, "parents": [DRIVE_FOLDER_ID]},
        media_body=MediaIoBaseUpload(io.BytesIO(image_bytes), mimetype=mime),
        fields="id, webViewLink",
    ).execute()
    return f.get("webViewLink", "")


def upload_and_link(image_bytes: bytes, filename: str, ref_id: str) -> str:
    """Upload ke Drive + tulis link ke kolom Link Bukti pada baris Ref ID.

    Return link, atau '' bila fitur mati/gagal (baris tetap tersimpan).
    """
    if not _drive_ready() or not image_bytes:
        return ""
    try:
        link = upload_drive(image_bytes, filename)
        if link:
            ws = _worksheet()
            refs = ws.col_values(8)
            row = refs.index(ref_id) + 1
            ws.update_cell(row, len(HEADERS), link)
        return link
    except Exception as e:
        print(f"Drive upload gagal: {type(e).__name__}: {e}")
        return ""


# ---------- Google Sheets (append-only) ----------

_sheet_cache = None


def _worksheet():
    global _sheet_cache
    if _sheet_cache is not None:
        return _sheet_cache
    if not SHEET_ID:
        raise RuntimeError("GOOGLE_SPREADSHEET_ID kosong")
    import gspread
    sa_raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    gc = gspread.service_account_from_dict(json.loads(sa_raw), scopes=GOOGLE_SCOPES) if sa_raw else gspread.service_account(filename=SA_FILE, scopes=GOOGLE_SCOPES)
    ws = gc.open_by_key(SHEET_ID).sheet1
    row1 = ws.row_values(1)
    if not row1:
        ws.append_row(HEADERS, value_input_option="RAW")
    elif row1[:11] == HEADERS[:11]:
        # Sheet lama (11/12 kolom) → tambahkan kolom yang kurang di ujung
        for i in range(len(row1), len(HEADERS)):
            ws.update_cell(1, i + 1, HEADERS[i])
    _sheet_cache = ws
    return ws


def _to_row(rec: dict) -> list:
    return [
        rec["tanggal"], rec["keterangan"], rec.get("nominal") or "", rec["arah"],
        rec["kategori"], "draft", rec["sumber_file"], rec["ref_id"],
        rec["confidence"], datetime.now().strftime("%Y-%m-%d %H:%M"), rec["catatan"],
        rec.get("caption", ""), rec.get("link_bukti", ""),
    ]


def append_sheet(rec: dict) -> str:
    """Append baris; dedupe via Ref ID. Return 'ok' | 'dup'."""
    ws = _worksheet()
    try:
        refs = ws.col_values(8)
    except Exception:
        refs = []
    if rec["ref_id"] in refs:
        return "dup"
    ws.append_row(_to_row(rec), value_input_option="RAW")
    return "ok"


def push_pending(rec: dict, error: str) -> None:
    with PENDING.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**rec, "_error": error, "_ts": int(time.time())}, ensure_ascii=False) + "\n")


def flush_pending(client: httpx.AsyncClient) -> int:
    """Kirim ulang antrean. Return jumlah yang masih tersisa."""
    if not PENDING.exists():
        return 0
    lines = PENDING.read_text(encoding="utf-8").strip().splitlines()
    PENDING.unlink(missing_ok=True)
    sisa = []
    for ln in lines:
        if not ln.strip():
            continue
        rec = json.loads(ln)
        rec.pop("_error", None)
        rec.pop("_ts", None)
        try:
            append_sheet(rec)
        except Exception as e:
            push_pending(rec, f"retry gagal: {e}")
            sisa.append(ln)
    return len(sisa)


# ---------- Telegram ----------

TG_API = "https://api.telegram.org/bot{token}/{method}"


async def tg_call(client: httpx.AsyncClient, method: str, **payload) -> dict:
    r = await client.post(TG_API.format(token=TG_TOKEN, method=method), json=payload, timeout=90)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description')}")
    return data["result"]


async def tg_send(client: httpx.AsyncClient, chat_id: int, text: str) -> None:
    with suppress(Exception):
        await tg_call(client, "sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")


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
        hasil = append_sheet(rec)
    except Exception as e:
        push_pending(rec, str(e))
        await tg_send(client, chat_id, f"⚠️ Ekstraksi OK, tapi kirim ke Sheets gagal ({type(e).__name__}). Masuk antrean, dikirim ulang otomatis.")
        return
    if hasil == "dup":
        await tg_send(client, chat_id, "♻️ Sudah pernah dicatat — dilewati.")
        return
    link = await asyncio.to_thread(upload_and_link, img.content, filename, rec["ref_id"])
    nominal = f"Rp{rec['nominal']:,}" if rec["nominal"] else "<i>belum terbaca</i>"
    baris_bukti = f'\n<a href="{link}">Bukti transfer</a>' if link else ""
    await tg_send(
        client, chat_id,
        f"✅ Draft tercatat ke Sheets\n"
        f"{rec['tanggal']} · {nominal} · {rec['arah']}\n"
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
                        chat = (upd.get("message") or {}).get("chat", {}).get("id")
                        if chat:
                            await tg_send(client, chat, f"❌ Gagal memproses: {type(e).__name__}: {e}")
            except Exception:
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
    else:
        print("Telegram nonaktif: isi TELEGRAM_BOT_TOKEN & TELEGRAM_ALLOWED_CHAT_IDS di .env")
    yield
    if task:
        task.cancel()


app = FastAPI(title="Transaction Recording Bot - Milestone 1", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "ok": True,
        "telegram": bool(TG_TOKEN and TG_ALLOWED),
        "sheets": bool(SHEET_ID),
        "ai": "vision" if AI_KEY else "mock",
        "drive": _drive_ready(),
        "pending": PENDING.exists(),
    }


@app.post("/api/extract")
async def api_extract(req: ExtractReq):
    async with httpx.AsyncClient() as client:
        raw = base64.b64decode(req.image_base64) if req.image_base64 else b""
        rec = await extract(client, req.filename, raw, req.caption)
        ref = "manual:" + re.sub(r"\W+", "-", req.filename)[:80]
        rec = {**rec, "sumber_file": req.filename, "ref_id": ref}
        try:
            hasil = append_sheet(rec)
        except Exception as e:
            push_pending(rec, str(e))
            return {**rec, "sheet": "pending", "error": str(e)}
        link = upload_and_link(raw, req.filename, ref)
        return {**rec, "sheet": hasil, "link_bukti": link}


if __name__ == "__main__":
    import uvicorn
    # HOST=0.0.0.0 untuk hosting (Render dkk); default tetap lokal agar tidak terekspos
    uvicorn.run(app, host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")))
