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
  → write_cash_report()    # Drive: folder tahun → file "Cash Report <tahun>" (copy
  │                        #   template if new + write period cell) → sheet TRANSAKSI
  │                        #   (SA); dedupe by Ref ID (col G); upload photo → col K;
  │                        #   append row A–K at first empty row; transfer = 2 paired
  │                        #   rows sharing the same Ref ID in col G
  → on failure: push_pending() → pending.jsonl
  → flush_pending()        # retried each polling cycle (no image → col K empty)
  → tg_send()              # reply: worksheet + row + receipt link
```

### Extraction Modes

- **Vision**: Enabled when `AI_API_KEY` set. Sends base64 image to `AI_BASE_URL/chat/completions`. Expects JSON back with `{tanggal, keterangan, nominal, arah, kategori, bank, kantong_tujuan}` — `bank` = kantong asal (BRI/BNI/Jago/TUNAI), `arah` may be `transfer` (then `kantong_tujuan` filled).
- **Mock**: Fallback. Date from `YYYY-MM-DD` regex in filename; amount from `Rp\d+` in caption; direction from keyword match; kantong empty (→ `CR_DEFAULT_BANK`).

### Cash Report writer (Drive + Sheets split)

- **Drive (OAuth user, scope `drive`)**: find/create year folder, find/copy template spreadsheet, upload receipt photo. SA cannot own files (`storageQuotaExceeded`).
- **Sheets (service account)**: all cell writes. Folder `Cash Report` is shared to `client_email` as Editor — files created inside inherit access.
- Target: file `Cash Report <tahun>` inside year folder → sheet `TRANSAKSI` (flat ledger, Bizschool style). Period cell `RECAP OVERVIEW!B3` = `=DATE(<tahun>,1,1)` written once on copy; RECAP/YEARLY/EXPENSE/INCOME are all derived via SUMIFS.
- Template built by `cash_report/build_template.py` (7 sheets, year-agnostic); verified by `cash_report/verify_template.py`.
- Columns A–K: Tanggal, Kantong, Masuk, Keluar, Kategori, Keterangan, Ref ID, Status, Catatan, Sumber File, Link Bukti.
- `Status` (col H) defaults to "draft" on all written rows. Transfer pairs = two rows sharing the same Ref ID in col G (pair marker; no separate column).
- Keterangan = LLM output with Telegram caption appended (`LLM — caption`) via `_gabung_keterangan`; no Confidence/Caption columns (dropped — no requirement, redundant).

### Failure Queue

`pending.jsonl` — JSONL file, one record per line. Retried before each polling cycle. **Not persistent across Render redeploys.**

## Key Config

| Var | Required | Purpose |
|-----|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot auth |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Yes | Whitelist (comma-sep) |
| `CASH_REPORT_FOLDER_ID` | Yes | Drive folder `Cash Report` (shared to SA) |
| `CASH_REPORT_TEMPLATE_ID` | Yes | Template spreadsheet to copy (from `build_template.py`) |
| `CR_DEFAULT_BANK` | No | Kantong fallback when extraction finds none (default TUNAI) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Cloud | Full SA JSON as string |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Local | Path to SA JSON file |
| `GOOGLE_OAUTH_CLIENT_ID/SECRET/REFRESH_TOKEN` | Drive | User OAuth, scope `drive` |
| `GOOGLE_DRIVE_FOLDER_ID` | No | Receipts folder (photo archive, col K) |
| `AI_API_KEY` | No | Enables vision extraction |
| `AI_BASE_URL` | No | Default: OpenAI |
| `AI_MODEL` | No | Default: gpt-4o-mini |
| `HOST` | Render | Set to `0.0.0.0` |

## Deployment

Hosted on Render (free tier). UptimeRobot pings `/health` every 5 min to prevent sleep.

Render build: `pip install -r requirements.txt`
Render start: `python main.py`
