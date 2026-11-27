# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then fill in values

# Run locally
python main.py

# Health check
curl http://localhost:8000/health

# Manual extraction (no Telegram needed)
curl -X POST http://localhost:8000/api/extract \
  -H "Content-Type: application/json" \
  -d '{"filename":"2024-01-15_receipt.jpg","caption":"Rp50000 makan siang"}'
# Run tests (31 tests — pending queue, reconciliation, QA, categories, ai_trace)
pytest -q
```

## Architecture

Single-file app: all logic in `main.py`. Two concurrent components:
1. **asyncio polling task** — long-polls Telegram, processes updates
2. **FastAPI server** — health check + manual extraction endpoint

### Data Flow

```
Photo/caption → Telegram → poll_loop() → handle_update()
  → extract()              # vision (OpenAI-compatible API) or mock (regex)
  → write_cash_report()    # Drive: folder tahun → file "Cash Report <tahun>" (copy
  │                        #   template if new + write period cell) → sheet TRANSAKSI
  │                        #   (SA); dedupe by Ref ID (col I); upload photo → col K;
  │                        #   append row A–K at first empty row; transfer = 2 paired
  │                        #   rows sharing the same Ref ID in col I
  → on failure: push_pending(chat_id) → pending.jsonl
  → flush_pending()        # retried each polling cycle; notifies origin chat
                           #   on success & on first failure only (_notif flag);
                           #   no image → col K empty
  → tg_send()              # reply: worksheet + row + receipt link
```

### Extraction Modes

- **Vision**: Enabled when `AI_API_KEY` set. Sends base64 image to `AI_BASE_URL/chat/completions`. Expects JSON back with `{tanggal, keterangan, nominal, arah, kategori, bank, kantong_tujuan}` — `bank` = kantong asal (BRI/BNI/Jago/UANG KAS), `arah` may be `transfer` (then `kantong_tujuan` filled).
- **Mock**: Fallback. Date from `YYYY-MM-DD` regex in filename; amount from `Rp\d+` in caption; direction from keyword match; kantong empty (→ `CR_DEFAULT_BANK`).

### Cash Report writer (Drive + Sheets split)

- **Drive — Apps Script Web App** (`APPS_SCRIPT_URL`/`SECRET`, kode `apps_script/Code.gs`): year folder, copy template, receipt photo upload, blank-sheet bootstrap. SA cannot own files (`storageQuotaExceeded`); OAuth user (Testing) expired every 7 days — Web App runs as the owner account, no expiring token. Drive **reads** (find spreadsheet id for reconciliation) stay on SA (scope `drive`).
- **Sheets (service account)**: all cell writes. Folder `Cash Report` is shared to `client_email` as Editor — files created inside inherit access.
- Target: file `Cash Report <tahun>` inside year folder → sheet `TRANSAKSI` (flat ledger, Bizschool style). Period cell `RECAP OVERVIEW!B3` = `=DATE(<tahun>,1,1)` written once on copy; RECAP/YEARLY/EXPENSE/INCOME are all derived via SUMIFS.
- Template built by `cash_report/build_template.py` (7 sheets, year-agnostic); verified by `cash_report/verify_template.py`.
- Columns A–K: Tanggal, Kantong, Masuk, Keluar, Kategori, Keterangan, Status, Catatan, Ref ID, Sumber File, Link Bukti.
- `Status` (col G) defaults to "draft" on all written rows. Transfer pairs = two rows sharing the same Ref ID in col I (pair marker; no separate column).
- Keterangan = LLM output with Telegram caption appended (`LLM — caption`) via `_gabung_keterangan`; no Confidence/Caption columns (dropped — no requirement, redundant).

### Failure Queue

`pending.jsonl` — JSONL file, one record per line. Retried before each polling cycle; records store `chat_id` so retry outcomes are notified (success, or first failure only via `_notif` flag). **Not persistent across Render redeploys.**

### Tanya-jawab (milestone 3, `cash_report/qa.py`)

Routing di `handle_update`: foto/document → ekstraksi, PDF → rekonsiliasi, teks → `handle_text`. Command `/total [bulan]`, `/rekap [bulan]`, `/help` deterministik (tanpa LLM); bahasa bebas lewat **satu panggilan tool-calling** (tools baca-saja `aggregate`/`list_rows`/`get_receipt`, maks3 putaran + ronde paksa). Angka dihitung kode; verified & draft disebut terpisah; transfer dikecualikan dari total. Jawaban LLM di-escape (`qa.amankan_html`) sebelum kirim (parse_mode=HTML).

### Rekonsiliasi mutasi bank (milestone 2, `reconciliation/`)

PDF mutasi (Telegram atau `/api/reconcile`) → render halaman (`pymupdf`) → vision AI per halaman → validasi keras (`statement_validator`: total, saldo jalan, saldo akhir) → normalisasi → cocok TRANSAKSI periode itu dengan kunci **(tanggal, kantong, debit, credit)** → tulis tab **RECONCILIATION** (bank+rekening+periode sama → **replace**, idempotent; TRANSAKSI tak disentuh; kolom uang Debit/Credit/Bank Balance/Sheet Debit/Sheet Credit diformat `"Rp"#,##0` ulang tiap tulis). Butuh env `BNI/BRI/JAGO_ACCOUNT_NUMBER`. Contoh file uji di `samples/`.

### LLM observability (`ai_trace.py`, Langfuse v5)

Optional Langfuse Cloud tracing of every AI call: `vision-extract` (main.py), `qa-tool-calling` (qa.py, usage accumulated across tool rounds), `recon-vision` (vision_extractor.py, per page). Helper `ai_trace.lacak()` context manager records success/failure; `ai_trace.diagnosa()` verifies credentials. Active only when `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are set (env `LANGFUSE_BASE_URL` for non-EU regions) and never under pytest. Only text is sent — images/credentials never leave. SDK must be **v5+**: v2 used the legacy `/api/public/ingestion` endpoint that Langfuse Cloud stopped accepting on 2026-11-16.

## Key Config

| Var | Required | Purpose |
|-----|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot auth |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Yes | Whitelist (comma-sep) |
| `CASH_REPORT_FOLDER_ID` | Yes | Drive folder `Cash Report` (shared to SA) |
| `CASH_REPORT_TEMPLATE_ID` | Yes | Template spreadsheet to copy (from `build_template.py`) |
| `CR_DEFAULT_BANK` | No | Kantong fallback when extraction finds none (default UANG KAS) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Cloud | Full SA JSON as string |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Local | Path to SA JSON file |
| `APPS_SCRIPT_URL/SECRET` | Drive | Web App Apps Script (pembuat file: folder, copy template, upload, create_sheet) — setup di README bagian Drive |
| `GOOGLE_DRIVE_FOLDER_ID` | No | Receipts folder (photo archive, col K) |
| `AI_API_KEY` | No | Enables vision extraction |
| `AI_BASE_URL` | No | Default: OpenAI |
| `AI_MODEL` | No | Default: gpt-4o-mini |
| `HOST` | Render | Set to `0.0.0.0` |
| `PORT` | Render | Dari `$PORT` Render (Render; jangan diubah) |
| `BNI_ACCOUNT_NUMBER`, `BRI_ACCOUNT_NUMBER`, `JAGO_ACCOUNT_NUMBER` | No* | Nomor rekening utk rekonsiliasi PDF mutasi (*kosong = PDF mutasi ditolak) |
| `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_RELEASE` | No | Observability — no-op tanpa DSN |
| `LOG_LEVEL` | No | Default `INFO` |

## Deployment

Hosted on Render (free tier). UptimeRobot pings `/health` every 5 min to prevent sleep.

Render build: `pip install -r requirements.txt`
Render start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
