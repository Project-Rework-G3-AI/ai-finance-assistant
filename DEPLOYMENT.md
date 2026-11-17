# Deployment — Render + UptimeRobot

Status: **aktif berjalan**. Dokumen ini mencatat bagaimana bot di-deploy dan dirawat.

- **URL aplikasi**: `https://ai-finance-assistant-z473.onrender.com`
- **Health check**: https://ai-finance-assistant-z473.onrender.com/health
- **Kode**: https://github.com/Project-Rework-G3-AI/ai-finance-assistant
- **Hosting**: Render — Free Web Service
- **Pinger**: UptimeRobot (HTTP check tiap 5 menit ke `/health`)

## Kenapa begini

Bot memakai **long polling** (koneksi keluar ke Telegram), jadi butuh proses yang selalu hidup. Free tier Render tidur setelah ~15 menit tanpa request masuk — UptimeRobot menahan supaya tidak tidur dengan memanggil `/health` berkala.

## Alur deployment

```
push ke main (GitHub)
   → Render build otomatis: pip install -r requirements.txt
   → start: python main.py  (HOST=0.0.0.0, PORT dari Render)
   → bot long-polling Telegram + endpoint API berjalan 24/7
UptimeRobot → GET /health tiap 5 menit → free tier tetap terjaga
```

## Konfigurasi di Render (Dashboard → Environment)

| Key | Nilai |
|---|---|
| `HOST` | `0.0.0.0` |
| `PORT` | (di-set Render; jangan diubah) |
| `TELEGRAM_BOT_TOKEN` | dari BotFather |
| `TELEGRAM_ALLOWED_CHAT_IDS` | daftar chat_id, pisah koma |
| `GOOGLE_SPREADSHEET_ID` | ID tujuan Sheet |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | **isi penuh file** `service_account.json` (JSON mentah) |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN` | (opsional) OAuth user untuk upload bukti ke Drive — lihat README "Setup Google Drive" |
| `GOOGLE_DRIVE_FOLDER_ID` | (opsional) ID folder tujuan arsip foto di Drive |
| `AI_API_KEY` | kunci vision (kosongkan = mode mock) |
| `AI_BASE_URL`, `AI_MODEL` | opsional (default OpenAI) |

Build/Start command:
- Build: `pip install -r requirements.txt`
- Start: `python main.py`

Kredensial **tidak** ada di repository — hanya di environment variable Render dan `.env` lokal (`.gitignore`).

## UptimeRobot

1. Tambah monitor **HTTP(s)**, URL: `https://ai-finance-assistant-z473.onrender.com/health`
2. Interval **5 menit**.
3. Kalau monitor berhenti (mis. saldo free habis / URL berubah), Render akan tidur → bot berhenti merespons.

## Verifikasi sehat

Buka health check; jawaban yang benar:

```json
{"ok": true, "telegram": true, "sheets": true, "ai": "vision", "pending": false}
```

- `telegram: false` → token/chat_id belum terisi atau belum terbaca.
- `sheets: false` → `GOOGLE_SPREADSHEET_ID` / `GOOGLE_SERVICE_ACCOUNT_JSON` belum terisi.
- `ai: "mock"` → `AI_API_KEY` kosong (ekstraksi hanya dari caption).
- `pending: true` → ada antrean yang belum terkirim ke Sheet (lihat log).

## Operasional

- **Ganti nilai env/key**: edit di Dashboard Render → redeploy otomatis. Jangan lupa sinkron `.env` lokal.
- **Log**: tab Logs di Render untuk melihat error polling/ekstraksi.
- **Bot lokal vs cloud — saling eksklusif.** Dua proses dengan token sama akan berebut `update_id` → balasan dobel/terproses ganda. Untuk demo lokal: matikan service di Render dulu, sebaliknya.
- **`pending.jsonl` di cloud bersifat sementara** — hilang saat redeploy (filesystem Render). Antrean hanya tahan kegagalan sementara, bukan penyimpanan.
- **Biaya**: Render Free + UptimeRobot free — tidak ada biaya bulanan selama kebijakan free tier berlaku.

## Troubleshooting

| Gejala | Kemungkinan | Tindakan |
|---|---|---|
| Bot diam total | Render tidur (pinger mati) / service crashed | Cek UptimeRobot & tab Logs; buka `/health` |
| `401 unauthorized` di log Telegram | Token salah/ganti | Update `TELEGRAM_BOT_TOKEN` |
| Append Sheets `invalid_grant` / permission | JSON salah tempel atau SA belum di-share Editor | Cek isi `GOOGLE_SERVICE_ACCOUNT_JSON` penuh; cek share Sheet |
| Balasan dobel | Dua bot berjalan (lokal + cloud) | Matikan salah satu |
| `sheets: false` padahal env sudah diisi | JSON invalid (kepotong) | Validasi: `python3 -c "import json,sys;json.loads(sys.stdin.read())" < service_account.json` |

## Batasan free tier

- Service **tidur** bila tidak ada pinger → ketergantungan pada UptimeRobot.
- Filesystem **tidak persisten** (pending hilang saat redeploy).
- Free tier hosting dapat berubah sewaktu-waktu oleh penyedia — untuk presentasi, siapkan fallback **bot lokal** (`python main.py` di laptop) yang tinggal dinyalakan setelah Render dimatikan.
