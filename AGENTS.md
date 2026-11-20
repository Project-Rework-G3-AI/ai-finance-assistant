# AGENTS.md

## Project Overview

Bot pencatatan transaksi: foto bukti transfer via Telegram → ekstraksi field (vision LLM / mock) → append ke Google Sheets (status `draft`, review manual). Python 3.12, FastAPI + long polling, satu file `main.py`. Tanpa database.

- Detail lengkap arsitektur & config → [CLAUDE.md](CLAUDE.md)
- Setup & alur kerja → [README.md](README.md)
- Deploy (Render + UptimeRobot) → [DEPLOYMENT.md](DEPLOYMENT.md)

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # isi nilainya

python main.py                                 # lokal: http://127.0.0.1:8000
curl http://localhost:8000/health              # verifikasi konfigurasi
curl -X POST http://localhost:8000/api/extract \
  -H "Content-Type: application/json" \
  -d '{"filename":"2026-01-15_receipt.jpg","caption":"Rp50000 beli kardus"}'
```

Tidak ada test framework — verifikasi via `/health` dan `/api/extract` sebelum dan sesudah mengubah kode.

## Architecture Notes

- Dua komponen dalam satu proses: task asyncio long-polling Telegram + server FastAPI. `HOST`/`PORT` dari env (default `127.0.0.1` lokal; `0.0.0.0` di hosting).
- Kredensial: Telegram & AI via env; **Drive = OAuth user** (`GOOGLE_OAUTH_*`, scope `drive`); **sel Cash Report = service account** (`GOOGLE_SERVICE_ACCOUNT_JSON`/`_FILE`, folder Cash Report di-share Editor ke SA). **Tidak pernah di kode/repo** — `.env`, `service_account.json`, `credentials.json`, `pending.jsonl` sudah di `.gitignore`.
- Tulis ke **Cash Report**: folder tahun → file `Cash Report <tahun>` (copy template Bizschool, sel periode ditulis) → sheet `TRANSAKSI` (flat ledger A–K) → dedupe Ref ID (kolom G) → upload foto ke Receipts (kolom K) → append baris (transfer = 2 baris berpasangan dengan Ref ID sama di kolom G). Gagal → antre `pending.jsonl`, retry tiap siklus polling.
- Semua angka dihitung kode; AI (vision) hanya mengisi field (`bank`, kategori, dll). Status baris selalu `draft` (kolom H) — konversi `verified` = review manual; query nanti hanya hitung `verified`.

## Code Style Guidelines

- Ikuti pola yang sudah ada di `main.py` (fungsi kecil, tanpa abstraksi baru yang tidak perlu).
- Tambah dependensi hanya kalau tidak bisa diselesaikan dengan standar library / yang sudah ada.
- Nama variabel deskriptif; ekstrak kondisi rumit jadi variabel boolean bernama jelas.
- Komentar hanya untuk alasan yang tidak terlihat dari kode.

## Common Workflows

- **Ubah kode**: edit `main.py` → test `/health` + `/api/extract` lokal → commit → push `main` (Render deploy otomatis) → cek `/health` produksi.
- **Ganti config/key**: ubah di env lokal **dan** Dashboard Render (sinkron), lalu redeploy.
- **Repo**: https://github.com/Project-Rework-G3-AI/ai-finance-assistant — `main` dilindungi PR (admin bisa langsung push).
