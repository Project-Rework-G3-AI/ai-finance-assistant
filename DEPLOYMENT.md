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
   → start: uvicorn main:app --host 0.0.0.0 --port $PORT
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
| `CR_DEFAULT_BANK` | opsional (default `UANG KAS`) |
| `APPS_SCRIPT_URL`, `APPS_SCRIPT_SECRET` | Apps Script Web App (Drive) — cari/buat folder, copy template, upload foto, bootstrap TEMPLATE. Detail setup: README bagian Drive |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | opsional — pelacakan LLM (prompt/output/token/biaya per panggilan vision & QA). Kosong = mati. SDK v5 (endpoint ingestion v4); `LANGFUSE_BASE_URL` hanya untuk region non-EU. Verifikasi: `python -c "import ai_trace; print(ai_trace.diagnosa())"` |
| `GOOGLE_DRIVE_FOLDER_ID` | (opsional) ID folder `Receipts` — arsip foto bukti |
| `AI_API_KEY` | kunci vision (kosongkan = mode mock) |
| `AI_BASE_URL`, `AI_MODEL` | opsional (default OpenAI) |
| `BNI_ACCOUNT_NUMBER`, `BRI_ACCOUNT_NUMBER`, `JAGO_ACCOUNT_NUMBER` | opsional — nomor rekening untuk rekonsiliasi PDF mutasi; **kosong = PDF mutasi ditolak** (lihat `samples/README.md` untuk nilai uji) |

Build/Start command:
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
  - Opsional, supaya `SENTRY_RELEASE` terisi otomatis tiap deploy: awali dengan
    `SENTRY_RELEASE=ai-finance-assistant@$(git rev-parse --short HEAD)` — kalau
    memakai ini, **hapus** `SENTRY_RELEASE` dari Environment (nilai di Environment
    menimpa nilai start command). Tanpa `.git` di folder service, release jadi
    kosong (tidak fatal). `SENTRY_*` lain diatur di bagian Sentry.

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

**Data sensitif disamarkan sebelum keluar dari server.** Aplikasi ini memproses bukti transaksi keuangan dan menyimpan kredensial di environment, jadi `sentry_setup.py` menetapkan `send_default_pii=False`, `max_request_body_size="never"`, `include_local_variables=False`, dan `before_send` yang menyamarkan:

- nilai variabel bernama token/secret/refresh_token/client_secret/Authorization
- token bot di dalam URL `api.telegram.org/bot<token>/...`
- kredensial di query string (`?api_key=`, `&token=`)
- nilai dict dengan kunci sensitif

`include_local_variables=False` perlu karena argumen fungsi ikut tersimpan sebagai variabel lokal. Tanpa opsi ini, byte gambar bukti transaksi dan isi dict transaksi ikut terkirim lewat stack trace — bukan lewat request body. Nama file, nomor baris, nama fungsi, dan pesan exception tetap utuh, jadi event masih berguna untuk debugging.

Gambar bukti transaksi tidak pernah dikirim karena body request tidak direkam.

**Error yang dilaporkan.** Selain exception yang lolos ke FastAPI (otomatis), ada 7 jalur yang menangani error sendiri dan sekarang memanggil `capture_exception()`:

| Lokasi | Kejadian |
|---|---|
| `extract()` | AI gagal, jatuh ke mode mock |
| `write_cash_report()` | upload Drive gagal (baris tetap tersimpan) |
| `handle_update()` | tulis Cash Report gagal, masuk antrean |
| `api_extract()` | tulis Cash Report gagal via endpoint API |
| `flush_pending()` | retry antrean gagal |
| `flush_pending()` | baris antrean rusak (bukan JSON valid) |
| `tg_send()` | pesan Telegram gagal terkirim (bot diblokir, 429) |
| `poll_loop()` | satu update gagal diproses |
| `poll_loop()` | loop Telegram gagal, ulang 3 detik |

Sebelum perubahan ini, jalur-jalur tersebut hanya menulis ke stdout atau tidak meninggalkan jejak sama sekali. `tg_send()` sebelumnya memakai `suppress(Exception)`, sehingga bot yang diblokir pengguna atau kena rate limit tidak meninggalkan bukti apa pun padahal pengguna tidak menerima balasan.

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
| Drive gagal: `Apps Script ... secret salah` / `HTTP 403/404` | `APPS_SCRIPT_SECRET` tidak cocok dengan Script Properties, atau Web App dideploy dengan akses terbatas | Cocokkan secret di Script Properties; deploy ulang dengan *Who has access: Anyone* (README bagian Drive). Gagal upload tidak mematikan bot — kolom Link Bukti kosong, error di log |
| Balasan dobel | Dua bot berjalan (lokal + cloud) | Matikan salah satu |
| Notif "⚠️ Percobaan ulang transaksi tertunda gagal" | Tulis Cash Report gagal berulang saat retry (SA kehilangan akses, Sheets down, env rusak) | Cek log & `/health`; pastikan SA masih Editor di folder & Sheet. Notifikasi muncul sekali per kegagalan beruntun (anti-spam) |
| `sheets: false` padahal env sudah diisi | JSON invalid (kepotong) | Validasi: `python3 -c "import json,sys;json.loads(sys.stdin.read())" < service_account.json` |

## Batasan free tier

- Service **tidur** bila tidak ada pinger → ketergantungan pada UptimeRobot.
- Filesystem **tidak persisten** (pending hilang saat redeploy).
- Free tier hosting dapat berubah sewaktu-waktu oleh penyedia — untuk presentasi, siapkan fallback **bot lokal** (`python main.py` di laptop) yang tinggal dinyalakan setelah Render dimatikan.
