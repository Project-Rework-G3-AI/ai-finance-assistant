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
```

No test framework configured. Test via `/health` and `/api/extract` endpoints.

## Architecture

Single-file app: all logic in `main.py`. Two concurrent components:
1. **asyncio polling task** — long-polls Telegram, processes updates
2. **FastAPI server** — health check + manual extraction endpoint

### Data Flow

```
Photo/caption → Telegram → poll_loop() → handle_update()
  → extract()              # vision (OpenAI-compatible API) or mock (regex)
  → write_cash_report()    # Drive: folder tahun → file "Cash Report {bank}" (copy
  │                        #   template if new, rename year) → monthly tab (SA);
  │                        #   dedupe by Ref ID (col K); upload photo → col J;
  │                        #   write row A–P; insert row before Sub Total if full
  │                        #   and rewrite SUM/saldo formulas
  → on failure: push_pending() → pending.jsonl
  → flush_pending()        # retried each polling cycle (no image → col J empty)
  → tg_send()              # reply: worksheet + row + receipt link
```

### Extraction Modes

- **Vision**: Enabled when `AI_API_KEY` set. Sends base64 image to `AI_BASE_URL/chat/completions`. Expects JSON back with `{tanggal, keterangan, nominal, arah, kategori, bank}`.
- **Mock**: Fallback. Date from `YYYY-MM-DD` regex in filename; amount from `Rp\d+` in caption; direction from keyword match; bank empty (→ `CR_DEFAULT_BANK`).

### Cash Report writer (Drive + Sheets split)

- **Drive (OAuth user, scope `drive`)**: find/create year folder, find/copy template spreadsheet, upload receipt photo. SA cannot own files (`storageQuotaExceeded`).
- **Sheets (service account)**: all cell writes. Folder `Cash Report` is shared to `client_email` as Editor — files created inside inherit access.
- Target: file `Cash Report {bank}` (bank from extraction, fallback `CR_DEFAULT_BANK`) inside year folder, monthly tab `Cash Report - <Bulan> <Tahun>` (must exist in template — error if missing).
- Template rules: header row 5, `Saldo Awal` row 6, data from row 7, `Sub Total` anchor in col B; `CR_TEMPLATE_YEAR` (default 2025) renamed on copy.
- Columns A–J = company format (G=Debet if masuk, H=Kredit if keluar, E/F always empty, I formula, J receipt link); K–P = audit (Ref ID, Status, Confidence, Caption, Catatan, Sumber File) — grid resized 10→16 + headers written once by `_ensure_extra`.
- `Status` (col L) defaults to "draft" on all written rows.

### Failure Queue

`pending.jsonl` — JSONL file, one record per line. Retried before each polling cycle. **Not persistent across Render redeploys.**

## Key Config

| Var | Required | Purpose |
|-----|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot auth |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Yes | Whitelist (comma-sep) |
| `CASH_REPORT_FOLDER_ID` | Yes | Drive folder `Cash Report` (shared to SA) |
| `CASH_REPORT_TEMPLATE_ID` | Yes | Template spreadsheet to copy |
| `CASH_REPORT_TEMPLATE_YEAR` | No | Template year to replace (default 2025) |
| `CR_DEFAULT_BANK` | No | Bank fallback when extraction finds none (default TUNAI) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Cloud | Full SA JSON as string |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Local | Path to SA JSON file |
| `GOOGLE_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN` | Drive | User OAuth, scope `drive` |
| `GOOGLE_DRIVE_FOLDER_ID` | No | Receipts folder (photo archive, col J) |
| `AI_API_KEY` | No | Enables vision extraction |
| `AI_BASE_URL` | No | Default: OpenAI |
| `AI_MODEL` | No | Default: gpt-4o-mini |
| `HOST` | Render | Set to `0.0.0.0` |

## Deployment

Hosted on Render (free tier). UptimeRobot pings `/health` every 5 min to prevent sleep.

Render build: `pip install -r requirements.txt`
Render start: `python main.py`
