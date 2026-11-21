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
| `GOOGLE_SERVICE_ACCOUNT_JSON` | **isi penuh file** `service_account.json` (JSON mentah) |
| `CASH_REPORT_FOLDER_ID`, `CASH_REPORT_TEMPLATE_ID` | folder Cash Report (di-share Editor ke SA) + ID template |
| `CR_DEFAULT_BANK` | opsional (default `TUNAI`) |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN` | OAuth user (scope `drive`) — cari folder/copy template/upload foto |
| `GOOGLE_DRIVE_FOLDER_ID` | (opsional) ID folder `Receipts` — arsip foto bukti |
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
{"ok": true, "telegram": true, "sheets": true, "ai": "vision", "pending": false, "sentry": true}
```

- `telegram: false` → token/chat_id belum terisi atau belum terbaca.
- `sheets: false` → `CASH_REPORT_FOLDER_ID` / `CASH_REPORT_TEMPLATE_ID` belum terisi.
- `ai: "mock"` → `AI_API_KEY` kosong (ekstraksi hanya dari caption).
- `pending: true` → ada antrean yang belum terkirim ke Sheet (lihat log).
- `sentry: false` → `SENTRY_DSN` kosong; bot tetap jalan, hanya observability yang mati.

## Observability (Sentry)

Sentry dipakai untuk menangkap error, tracing request, dan log terpusat. Konfigurasinya ada di `sentry_setup.py`, dipanggil sekali di awal `main.py`.

**Yang perlu disiapkan:** satu project Sentry platform **Python → FastAPI**, lalu salin **DSN**-nya. DSN bukan token API: DSN hanya untuk *mengirim* data, tidak bisa dipakai membaca project. Jadi tidak perlu membuat Auth Token.

| Key | Nilai | Wajib |
|---|---|---|
| `SENTRY_DSN` | DSN dari Settings → Projects → Client Keys | untuk aktif |
| `SENTRY_ENVIRONMENT` | `production` di Render, `development` di lokal | disarankan |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` (10% request direkam) | opsional |
| `SENTRY_RELEASE` | mis. `ai-finance-assistant@a1b2c3d` | opsional |
| `LOG_LEVEL` | `INFO` (default), `DEBUG` saat investigasi | opsional |

`SENTRY_ENVIRONMENT` hanya label: nilainya ditempelkan ke setiap event, tidak mengubah cara SDK bekerja. Yang berubah ada di sisi dashboard Sentry:

- **Filter environment.** Dashboard punya pemilih environment; filter yang tidak cocok akan menyembunyikan issue. Bila variabel ini salah isi, error produksi bisa tidak terlihat karena tersaring atau tercampur dengan error dari laptop.
- **Alert rules.** Aturan alert bisa dibatasi ke environment tertentu, mis. hanya kirim notifikasi untuk `production`.
- **Release health.** Angka crash-free session dan user dihitung per environment.
- **Quota.** Semua environment memakai kuota project yang sama, jadi error saat development ikut memakan jatah.

Kalau dikosongkan, SDK memakai `production` (default Sentry). Untuk lokal, isi `development` secara eksplisit agar tidak tercampur.

Tanpa `SENTRY_DSN`, seluruh fungsi observability jadi no-op dan bot berjalan seperti biasa.

**Data sensitif disamarkan sebelum keluar dari server.** Aplikasi ini memproses bukti transaksi keuangan dan menyimpan kredensial di environment, jadi `sentry_setup.py` menetapkan `send_default_pii=False`, `max_request_body_size="never"`, dan `before_send` yang menyamarkan:

- nilai variabel bernama token/secret/refresh_token/client_secret/Authorization
- token bot di dalam URL `api.telegram.org/bot<token>/...`
- kredensial di query string (`?api_key=`, `&token=`)
- nilai dict dengan kunci sensitif, termasuk di variabel lokal stack trace

Gambar bukti transaksi tidak pernah dikirim karena body request tidak direkam.

**Error yang dilaporkan.** Selain exception yang lolos ke FastAPI (otomatis), ada 7 jalur yang menangani error sendiri dan sekarang memanggil `capture_exception()`:

| Lokasi | Kejadian |
|---|---|
| `extract()` | AI gagal, jatuh ke mode mock |
| `write_cash_report()` | upload Drive gagal (baris tetap tersimpan) |
| `handle_update()` | tulis Cash Report gagal, masuk antrean |
| `api_extract()` | tulis Cash Report gagal via endpoint API |
| `flush_pending()` | retry antrean gagal |
| `poll_loop()` | satu update gagal diproses |
| `poll_loop()` | loop Telegram gagal, ulang 3 detik |

Sebelum perubahan ini, ketujuh jalur tersebut hanya menulis ke stdout atau tidak meninggalkan jejak sama sekali.

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
