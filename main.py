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
from cash_report import categories as KAT
from cash_report import qa

# ---------- Bank statement reconciliation ----------
from reconciliation.extractor import extract_bank_statement
from reconciliation.statement_validator import validate_statement
from reconciliation.sheets_reader import get_cash_report_transactions
from reconciliation.normalizer import (
    normalize_statement,
    normalize_sheet_transactions,
)
from reconciliation.matcher import (
    reconcile_transactions,
    summarize_reconciliation,
)
from reconciliation.report_writer import write_reconciliation_report

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
CR_DEFAULT_BANK = os.getenv("CR_DEFAULT_BANK", "UANG KAS").strip().upper()
AI_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini").strip()
ACCOUNT_MAPPING = {
    "BNI": {
        "account_number": (os.getenv("BNI_ACCOUNT_NUMBER") or "").strip(),
        "pocket": "BNI",
    },
    "BRI": {
        "account_number": (os.getenv("BRI_ACCOUNT_NUMBER") or "").strip(),
        "pocket": "BRI",
    },
    "JAGO": {
        "account_number": (os.getenv("JAGO_ACCOUNT_NUMBER") or "").strip(),
        "pocket": "Jago",
    },
}

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

def _parse_tanggal_ke_datetime(raw_tanggal: object) -> tuple[datetime, bool]:
    """Mengubah nilai tanggal dari AI menjadi datetime.

    Mengembalikan (dt, valid_dari_ai).
    """
    if isinstance(raw_tanggal, datetime):
        return raw_tanggal, True

    teks = str(raw_tanggal or "").strip()
    if not teks:
        return datetime.now(), False

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(teks[:19], fmt), True
        except ValueError:
            continue

    with suppress(ValueError):
        return datetime.fromisoformat(teks), True

    return datetime.now(), False


async def _vision_extract(client: httpx.AsyncClient, filename: str, image_bytes: bytes, caption: str) -> dict:
    b64 = base64.b64encode(image_bytes).decode()
    mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    prompt = (
        "Ekstrak data transaksi dari bukti ini. Balas HANYA JSON tanpa teks lain: "
        '{"tanggal":"YYYY-MM-DD HH:MM:SS","keterangan":"...","nominal":number,'
        '"arah":"masuk|keluar|transfer — bukti dari sisi pembayar '
        '(Pembayaran QRIS ke [merchant], Transfer ke [penerima]) berarti keluar; '
        'masuk hanya bila bukti menunjukkan dana diterima (mutasi masuk, pembayaran dari pembeli)",'
        f'"kategori":"satu dari: {KAT.PROMPT_KATEGORI}",'
        '"bank":"kantong asal dana — salah satu dari: BRI, BNI, Jago, UANG KAS; '
        'kosong bila tidak terbaca",'
        '"kantong_tujuan":"hanya bila arah=transfer — kantong tujuan: '
        'BRI, BNI, Jago, UANG KAS; kosong bila bukan transfer"}'
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
    text = r.json()["choices"][0]["message"]["content"] or ""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(
            "balasan AI bukan JSON" + (" (content kosong)" if not text else "")
        )
    data = json.loads(m.group(0))
    arah = str(data.get("arah", "")).lower()
    keterangan = _gabung_keterangan(str(data.get("keterangan") or ""), caption, filename)
    tanggal_dt, tanggal_valid = _parse_tanggal_ke_datetime(data.get("tanggal"))

    notes = []
    if not tanggal_valid:
        notes.append("tanggal tidak terbaca — pakai hari ini")
    if not data.get("nominal"):
        notes.append("nominal tidak terbaca — isi manual")
    if not str(data.get("bank") or "").strip():
        notes.append("kantong tidak terbaca — pakai default")
    kategori_mentah = str(data.get("kategori") or "").strip()
    kategori = KAT.normalize(kategori_mentah)
    if kategori == KAT.PERLU_DITINJAU:
        if kategori_mentah:
            notes.append(f"kategori '{kategori_mentah}' tidak dikenali — isi manual")
        else:
            notes.append("kategori tidak terbaca — isi manual")
    catatan = "Ekstraksi AI — wajib ditinjau sebelum dipakai."
    if notes:
        catatan += " (" + ", ".join(notes) + ")"

    return {
        "tanggal": tanggal_dt,
        "keterangan": keterangan,
        "nominal": int(data["nominal"]) if data.get("nominal") else None,
        "arah": arah if arah in ("masuk", "keluar", "transfer") else "keluar",
        "kategori": kategori,
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


# ---------- Google Drive ----------
# Split: baca (cari id spreadsheet utk rekonsiliasi) = service account (scope
# drive penuh, tidak pernah kedaluwarsa). Operasi yang MEMBUAT file (folder,
# copy template, upload foto) = Apps Script Web App — SA tidak bisa membuat
# file (kuota 0, storageQuotaExceeded), dan OAuth user Testing kedaluwarsa
# tiap7 hari (invalid_grant, lihat README bagian Drive).

APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "").strip()
APPS_SCRIPT_SECRET = os.getenv("APPS_SCRIPT_SECRET", "").strip()


def _drive_ready() -> bool:
    return bool(DRIVE_FOLDER_ID and APPS_SCRIPT_URL and APPS_SCRIPT_SECRET)


def apps_script_call(action: str, payload: dict) -> dict:
    """Panggil Web App Apps Script. Return body['data'] atau raise RuntimeError.

    Sinkron — googleapiclient lama juga blocking, dan dipakai script utilitas
    (build_template, migrasi) di luar event loop. follow_redirects wajib:
    Web App bisa menjawab 302 sebelum /exec final.
    """
    if not (APPS_SCRIPT_URL and APPS_SCRIPT_SECRET):
        raise RuntimeError("APPS_SCRIPT_URL / APPS_SCRIPT_SECRET belum diisi")
    body = {"secret": APPS_SCRIPT_SECRET, "action": action, **payload}
    with httpx.Client(follow_redirects=True, timeout=30) as cli:
        r = cli.post(APPS_SCRIPT_URL, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"Apps Script HTTP {r.status_code}: {r.text[:200]}")
    out = r.json()
    if not out.get("ok"):
        raise RuntimeError(f"Apps Script {action} gagal: {out.get('error')}")
    return out.get("data") or {}


_sa_drive = None


def _drive():
    """Drive API client (service account) — hanya untuk BACA (files.list)."""
    global _sa_drive
    if _sa_drive is None:
        from google.oauth2 import service_account as sa_credentials
        from googleapiclient.discovery import build

        sa_raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        creds = (
            sa_credentials.Credentials.from_service_account_info(
                json.loads(sa_raw), scopes=GOOGLE_SCOPES
            )
            if sa_raw
            else sa_credentials.Credentials.from_service_account_file(
                SA_FILE, scopes=GOOGLE_SCOPES
            )
        )
        _sa_drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return _sa_drive


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
    """Upload foto ke folder Receipts via Apps Script. Return webViewLink."""
    import base64

    mime = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    data = apps_script_call(
        "upload",
        {
            "filename": filename,
            "folder_id": DRIVE_FOLDER_ID,
            "content_base64": base64.b64encode(image_bytes).decode(),
            "mime": mime,
        },
    )
    return data.get("link", "")


def _find_or_create_folder(folder_name: str, parent_id: str) -> str:
    """Folder di Drive (via Apps Script): cari, kalau tidak ada buat."""
    data = apps_script_call("folder", {"name": folder_name, "parent_id": parent_id})
    return data["id"]


def _find_or_create_spreadsheet(year: str, year_folder_id: str) -> dict:
    """Spreadsheet gabungan 'Cash Report {tahun}': cari, kalau tidak ada copy template (via Apps Script)."""
    if not CR_TEMPLATE_ID:
        raise RuntimeError("CASH_REPORT_TEMPLATE_ID kosong")
    data = apps_script_call(
        "copy_template",
        {
            "name": f"Cash Report {year}",
            "parent_id": year_folder_id,
            "template_id": CR_TEMPLATE_ID,
        },
    )
    out = {"id": data["id"], "name": data["name"], "webViewLink": data.get("link", "")}
    if data.get("created"):
        _init_year_dates(out["id"], year)
    return out


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
    raw_tgl = rec.get("tanggal")
    if isinstance(raw_tgl, datetime):
        dt = raw_tgl
    elif isinstance(raw_tgl, str) and raw_tgl.strip():
        try:
            dt = datetime.fromisoformat(raw_tgl.strip())
        except ValueError:
            dt = datetime.now(ZoneInfo("Asia/Jakarta"))
    else:
        dt = datetime.now(ZoneInfo("Asia/Jakarta"))

    tanggal = dt.strftime("%Y-%m-%d %H:%M:%S")
    year = dt.strftime("%Y")
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
    # Format kolom Tanggal diseragamkan: penulisan datetime (jam transaksi) membuat
    # Sheets memakai format otomatis yyyy-mm-dd h:mm:ss sehingga tampilan tercampur
    # dengan baris lama d-MMM-yy. Format eksplisit ditulis ulang setelah append.
    ws.format(
        f"A{row}:A{row + len(values) - 1}",
        {"numberFormat": {"type": "DATE", "pattern": "d-MMM-yy"}},
    )
    return {"status": "ok", "worksheet": ws.title, "row": row, "link": link}


def push_pending(rec: dict, error: str) -> None:
    with PENDING.open("a", encoding="utf-8") as f:
        # default=str: rec["tanggal"] kini bisa datetime — tanpa ini
        # json.dumps TypeError dan transaksi hilang saat tulis gagal.
        f.write(json.dumps({**rec, "_error": error, "_ts": int(time.time())},
                           ensure_ascii=False, default=str) + "\n")


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
                                   ensure_ascii=False, default=str))

    # Tulis ulang hanya bila masih ada sisa; file kosong dihapus agar /health
    # melaporkan pending=false dengan benar.
    if sisa:
        PENDING.write_text("\n".join(sisa) + "\n", encoding="utf-8")
    else:
        PENDING.unlink(missing_ok=True)
    return len(sisa)


# ---------- Rekonsiliasi mutasi bank ----------

async def reconcile_bank_statement(pdf_bytes: bytes) -> dict:
    """Ekstrak PDF, validasi, cocokkan dengan Cash Report, lalu tulis laporan."""
    if not AI_KEY:
        raise RuntimeError("AI_API_KEY wajib diisi untuk ekstraksi mutasi bank")

    statement = await extract_bank_statement(
        pdf_bytes=pdf_bytes,
        ai_key=AI_KEY,
        ai_base=AI_BASE,
        ai_model=AI_MODEL,
    )

    validation = validate_statement(statement)
    if not validation["is_valid"]:
        raise ValueError(
            "Validasi mutasi bank gagal: " + "; ".join(validation["errors"])
        )

    bank_transactions = normalize_statement(statement, ACCOUNT_MAPPING)

    # Ambil ulang data Cash Report setiap upload agar hasil selalu dibandingkan
    # dengan isi spreadsheet terbaru, termasuk bila PDF diunggah berulang.
    drive_service = _drive()
    sheets_service = _sheets()
    spreadsheet_id, raw_sheet_transactions = get_cash_report_transactions(
        drive_service,
        sheets_service,
        statement,
    )

    sheet_transactions, normalization_errors = normalize_sheet_transactions(
        raw_sheet_transactions
    )

    results = reconcile_transactions(
        bank_transactions=bank_transactions,
        sheet_transactions=sheet_transactions,
        period_start=statement["period_start"],
        period_end=statement["period_end"],
    )
    summary = summarize_reconciliation(results)

    report_rows_written, rekon_gid = write_reconciliation_report(
        sheets_service=sheets_service,
        spreadsheet_id=spreadsheet_id,
        statement=statement,
        reconciliation_results=results,
    )

    return {
        "statement": statement,
        "validation": validation,
        "summary": summary,
        "normalization_errors": normalization_errors,
        "report_rows_written": report_rows_written,
        "spreadsheet_id": spreadsheet_id,
        # #gid = langsung membuka tab RECONCILIATION, bukan sheet pertama
        "report_url": (
            f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            f"#gid={rekon_gid}"
        ),
    }


async def handle_bank_statement_pdf(
    client: httpx.AsyncClient,
    chat_id: int,
    file_id: str,
    filename: str,
) -> None:
    """Unduh PDF mutasi dari Telegram dan jalankan rekonsiliasi."""
    info = await tg_call(client, "getFile", file_id=file_id)
    url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{info['file_path']}"
    response = await client.get(url, timeout=120)
    response.raise_for_status()

    try:
        result = await reconcile_bank_statement(response.content)
    except Exception as e:
        log.exception("Rekonsiliasi mutasi bank gagal: %s", filename)
        await tg_send(
            client,
            chat_id,
            f"❌ Rekonsiliasi gagal ({type(e).__name__}): {e}",
        )
        return

    summary = result["summary"]
    report_text = (
        f'\nBaris laporan ditulis: {result["report_rows_written"]}'
        f'\n<a href="{result["report_url"]}">Buka Cash Report (tab RECONCILIATION)</a>'
    )
    await tg_send(
        client,
        chat_id,
        "✅ Rekonsiliasi selesai\n"
        f"Bank: {result['statement'].get('bank')}\n"
        f"Rekening: {result['statement'].get('account_number')}\n"
        f"Periode: {result['statement'].get('period_start')} s.d. "
        f"{result['statement'].get('period_end')}\n"
        f"Total transaksi: {summary.get('total', 0)}\n"
        f"Matched: {summary.get('matched', 0)}\n"
        f"Bank only: {summary.get('bank_only', 0)}\n"
        f"Sheet only: {summary.get('sheet_only', 0)}\n"
        f"Perlu ditinjau: {summary.get('needs_review', 0)}"
        f"{report_text}",
    )


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


async def handle_text(client: httpx.AsyncClient, chat_id: int, text: str) -> None:
    """Command / atau pertanyaan bebas (milestone 3). Kegagalan -> bantuan."""
    try:
        if text.startswith("/"):
            reply = await asyncio.to_thread(qa.command_reply, text, _qa_load_rows)
        else:
            # jawaban LLM di-escape: kutipan isi sheet boleh memuat '<',
            # tapi parse_mode=HTML menolak tag tak dikenal (bug /help dulu)
            reply = qa.amankan_html(await qa.answer_question(client, text, _qa_load_rows))
    except Exception:
        log.exception("Tanya-jawab gagal")
        reply = qa.FALLBACK
    await tg_send(client, chat_id, reply or qa.FALLBACK)


def _qa_load_rows(year: str) -> list[list[str]]:
    """Baca ledger tahun berjalan (provisioning sama dengan jalur tulis)."""
    if not CR_FOLDER_ID or not CR_TEMPLATE_ID:
        raise RuntimeError("CASH_REPORT_FOLDER_ID / CASH_REPORT_TEMPLATE_ID belum diisi")
    year_folder = _find_or_create_folder(str(year), CR_FOLDER_ID)
    ss_file = _find_or_create_spreadsheet(str(year), year_folder)
    sh = _open_spreadsheet(ss_file["id"])
    try:
        ws = sh.worksheet("TRANSAKSI")
    except Exception as e:
        raise FileNotFoundError("Sheet TRANSAKSI tidak ditemukan — periksa CASH_REPORT_TEMPLATE_ID") from e
    return ws.get_values("A2:K")


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

    # PDF diperlakukan sebagai mutasi bank, bukan receipt transaksi.
    if doc and (
        doc.get("mime_type") == "application/pdf"
        or str(doc.get("file_name", "")).lower().endswith(".pdf")
    ):
        await handle_bank_statement_pdf(
            client=client,
            chat_id=chat_id,
            file_id=doc["file_id"],
            filename=doc.get("file_name") or "bank_statement.pdf",
        )
        return

    if not doc and not photo:
        # Routing: foto/dokumen ke ekstraksi; teks ke tanya-jawab (lihat qa.py).
        text = str(msg.get("text") or "").strip()
        if text:
            await handle_text(client, chat_id, text)
        else:
            await tg_send(
                client,
                chat_id,
                "Kirim foto bukti transaksi (JPG/PNG) atau file PDF mutasi bank.",
            )
        return

    if photo:
        fid = photo[-1]["file_id"]
        filename = f"photo_{msg.get('date', int(time.time()))}.jpg"
    else:
        mime = (doc.get("mime_type") or "")
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
    baris_kantong = ""
    if not str(rec.get("bank") or "").strip():
        # Bukti: kantong default mengotori saldo UANG KAS (kas operasional) di tab
        # ACCOUNT — direkonsiliasikan stakeholder ke buku kas fisik. Sorot di balasan.
        baris_kantong = (
            f"\n⚠️ Kantong asal tidak terbaca — ditulis sebagai <b>{kantong} (default)</b>;"
            " koreksi di Sheet bila bukan kas."
        )
    await tg_send(
        client, chat_id,
        f"✅ Draft tercatat — {hasil['worksheet']} baris {hasil['row']}\n"
        f"{rec['tanggal']} · {nominal} · {arah_teks}\n"
        f"Keterangan: {rec['keterangan']}{baris_kantong}{baris_bukti}\n"
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


class ReconcileReq(BaseModel):
    filename: str = "bank_statement.pdf"
    pdf_base64: str
    

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


@app.post("/api/reconcile")
async def api_reconcile(req: ReconcileReq):
    """Endpoint untuk menguji/memanggil rekonsiliasi PDF tanpa Telegram."""
    try:
        pdf_bytes = base64.b64decode(req.pdf_base64, validate=True)
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("File yang dikirim bukan PDF yang valid")
        result = await reconcile_bank_statement(pdf_bytes)
        return {
            "ok": True,
            "filename": req.filename,
            "bank": result["statement"].get("bank"),
            "account_number": result["statement"].get("account_number"),
            "period_start": result["statement"].get("period_start"),
            "period_end": result["statement"].get("period_end"),
            "summary": result["summary"],
            "normalization_errors": result["normalization_errors"],
            "report_rows_written": result["report_rows_written"],
            "report_url": result["report_url"],
        }
    except Exception as e:
        log.exception("API reconciliation gagal")
        raise HTTPException(status_code=400, detail=f"{type(e).__name__}: {e}") from e


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
