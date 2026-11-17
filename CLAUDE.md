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

Single-file app: all logic in `main.py` (339 lines). Two concurrent components:
1. **asyncio polling task** — long-polls Telegram, processes updates
2. **FastAPI server** — health check + manual extraction endpoint

### Data Flow

```
Photo/caption → Telegram → poll_loop() → handle_update()
  → extract()          # vision (OpenAI-compatible API) or mock (regex)
  → append_sheet()     # dedupes by Ref ID (col 8); returns "ok"/"dup"
  → on failure: push_pending() → pending.jsonl
  → flush_pending()    # retried each polling cycle before new updates
  → tg_send()          # reply to user
```

### Extraction Modes

- **Vision**: Enabled when `AI_API_KEY` set. Sends base64 image to `AI_BASE_URL/chat/completions`. Expects JSON back with `{tanggal, keterangan, nominal, arah, kategori}`.
- **Mock**: Fallback. Date from `YYYY-MM-DD` regex in filename; amount from `Rp\d+` in caption; direction from keyword match.

### Google Sheets

- Auth: service account JSON — either file path (`GOOGLE_SERVICE_ACCOUNT_FILE`) or full JSON string in env (`GOOGLE_SERVICE_ACCOUNT_JSON`, used on Render).
- `_worksheet()`: lazy-loads and caches worksheet; auto-creates header row; auto-migrates "Caption" column.
- Schema: 12 columns — Tanggal, Keterangan, Nominal, Arah, Kategori, Status, Sumber File, Ref ID, Confidence, Tanggal Input, Catatan, Caption.
- `Status` defaults to "draft" on all appended rows.

### Failure Queue

`pending.jsonl` — JSONL file, one record per line. Retried before each polling cycle. **Not persistent across Render redeploys.**

## Key Config

| Var | Required | Purpose |
|-----|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot auth |
| `TELEGRAM_ALLOWED_CHAT_IDS` | Yes | Whitelist (comma-sep) |
| `GOOGLE_SPREADSHEET_ID` | Yes | Target sheet |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Cloud | Full SA JSON as string |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Local | Path to SA JSON file |
| `AI_API_KEY` | No | Enables vision extraction |
| `AI_BASE_URL` | No | Default: OpenAI |
| `AI_MODEL` | No | Default: gpt-4o-mini |
| `HOST` | Render | Set to `0.0.0.0` |

## Deployment

Hosted on Render (free tier). UptimeRobot pings `/health` every 5 min to prevent sleep.

Render build: `pip install -r requirements.txt`
Render start: `python main.py`
