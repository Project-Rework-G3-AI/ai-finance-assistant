# Bot Pencatatan Transaksi — Milestone 1: Telegram → Ekstraksi → Google Sheets

Bot Telegram terima foto/screenshot bukti transaksi → ekstraksi field → append ke Google Sheets (status `draft`, review manual di Sheet). Tanpa database.

Deploy aktif: https://ai-finance-assistant-z473.onrender.com/health — detail di [DEPLOYMENT.md](DEPLOYMENT.md).

## Arsitektur

```mermaid
flowchart LR
    U["Pengguna<br/>(Finance/Admin)"] -->|"kirim foto + caption"| TG["Telegram API<br/>(cloud)"]
    TG -->|"getUpdates<br/>long polling, koneksi keluar"| BOT["Bot — main.py<br/>FastAPI + asyncio<br/>(berjalan di lokal)"]

    BOT -->|"baca gambar"| EXT{"Ekstraksi"}
    EXT -->|"AI_API_KEY terisi"| VIS["Vision LLM<br/>(chat/completions)"]
    EXT -->|"tanpa AI / AI gagal"| MOCK["Mock<br/>nama file + caption"]
    VIS -.->|"gagal → fallback"| MOCK

    BOT -->|"Ref ID duplikat?"| DUP{"sudah<br/>ada?"}
    DUP -->|"ya"| SKIP["balasan: dilewati"]
    DUP -->|"tidak"| SHEET[("Google Sheets<br/>status draft<br/>(cloud)")]
    SHEET -->|"upload foto baru<br/>(opsional)"| DRIVE["Google Drive<br/>Link Bukti<br/>(cloud)"]
    SHEET -->|"gagal"| PEND["pending.jsonl<br/>(lokal)"]
    PEND -->|"retry tiap siklus"| SHEET

    SHEET -->|"review manual:<br/>draft → verified"| U
    W["Browser lokal<br/>GET /health<br/>POST /api/extract"] --> BOT

    classDef cloud fill:#1e3a5f,stroke:#3b82f6,color:#fff
    classDef local fill:#14532d,stroke:#22c55e,color:#fff
    class TG,SHEET,VIS,DRIVE cloud
    class BOT,MOCK,PEND,W local
```

- Satu proses di lokal: polling Telegram + endpoint API berjalan bersamaan; semua koneksi **keluar** (internet), tanpa server publik.
- Mode vision (AI) dipakai bila `AI_API_KEY` ada; selalu fallback ke mock agar alur tidak pernah putus.
- Sheets = tujuan akhir (append-only); `pending.jsonl` = penahan gagal, bukan penyimpanan utama.

## Setup

```bash
cd bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # lalu isi
python main.py              # server di http://127.0.0.1:8000
```

Isi `.env` minimal:

1. `TELEGRAM_BOT_TOKEN` — dari @BotFather.
2. `TELEGRAM_ALLOWED_CHAT_IDS` — chat_id pengguna yang boleh (cek via @userinfobot), pisahkan koma.

## Setup Google Sheets (service account)

Gratis, tanpa billing, sekali setup (~5 menit), kunci tidak kedaluwarsa.

1. **Buat project** — https://console.cloud.google.com → dropdown project → **New Project** → Create.
2. **Aktifkan API** — menu **APIs & Services** → **Library** → cari "Google Sheets API" → **Enable**.
3. **Buat service account** — **APIs & Services** → **Credentials** → **Create Credentials** → **Service account** → nama bebas → Create and Continue → skip role → **Done**.
4. **Unduh kunci** — klik akun yang baru dibuat → tab **Keys** → **Add Key** → **Create new key** → **JSON**.
5. **Pasang ke project**:
   ```bash
   cp ~/Downloads/<file>.json service_account.json   # sudah masuk .gitignore
   ```
6. **Ambil email service account**:
   ```bash
   .venv/bin/python -c "import json;print(json.load(open('service_account.json'))['client_email'])"
   ```
7. **Siapkan Sheet** — buat Sheet baru (kas Operasional) → **Share** → tempel email service account → role **Editor** → centang "Don't send". Salin **Spreadsheet ID** dari URL `docs.google.com/spreadsheet/d/`**`ID`**`/edit`.
8. **Isi `.env`**:
   ```
   GOOGLE_SPREADSHEET_ID=<ID>
   GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
   ```

Verifikasi: `curl http://127.0.0.1:8000/health` → `"sheets": true`.

Troubleshooting: append gagal "insufficient permissions" = email service account (langkah 6) belum dapat akses Editor di Sheet (langkah 7).

Opsional AI: isi `AI_API_KEY` (+ `AI_BASE_URL`/`AI_MODEL` bila pakai provider lain) untuk ekstraksi vision. Tanpa itu = mode mock (tanggal dari nama file, nominal dari caption).

## Setup Google Drive (opsional — arsip bukti transfer)

Foto yang diterima juga diunggah ke Google Drive; tautannya ditulis ke kolom `Link Bukti` supaya bisa dibuka langsung dari Sheet (memenuhi UC-02). Fitur ini **opsional** — tanpa konfigurasi, bot tetap jalan normal.

Upload memakai **OAuth akun user** (bukan service account): Google memblokir service account membuat file sendiri (error `storageQuotaExceeded`), kecuali lewat Shared Drive yang butuh Google Workspace.

1. **Aktifkan Drive API** — Google Cloud Console → **APIs & Services** → **Library** → cari "Google Drive API" → **Enable**.
2. **OAuth consent screen** — **APIs & Services** → **OAuth consent screen** → User Type **External** → isi app name/email → **Save** → tab **Audience/Testing** → **+ Add users** → tambahkan Gmail yang akan jadi pemilik foto (mode Testing cukup, tidak perlu verifikasi Google).
3. **Buat OAuth client** — **Credentials** → **Create Credentials** → **OAuth client ID** → Application type **Desktop app** → Create → **Download JSON** → simpan sebagai `credentials.json` di folder `bot/` (sudah masuk `.gitignore`).
4. **Ambil refresh token (sekali saja)** — jalankan dua perintah ini. Perhatian: baris penutup `PY` harus **tepat di kolom paling kiri** (tanpa spasi); kalau terminal menampilkan prompt `>` terus, ketik `PY` lalu Enter.

```bash
.venv/bin/pip install google-auth-oauthlib   # sudah di requirements.txt
.venv/bin/python - <<'PY'
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json", ["https://www.googleapis.com/auth/drive.file"])
creds = flow.run_local_server(port=0)
print("REFRESH_TOKEN=" + creds.refresh_token)
PY
```

   Browser terbuka → login Gmail tujuan → izinkan → salin nilai `REFRESH_TOKEN` dari terminal.
5. **Buat folder tujuan** — di Drive akun yang sama, mis. `Receipts 2026` → salin **Folder ID** dari URL `drive.google.com/drive/folders/`**`ID`**. *(Tidak perlu share — file nanti milik akun ini.)*
6. **Isi `.env`**:
   ```
   GOOGLE_OAUTH_CLIENT_ID=<client id dari langkah 3>
   GOOGLE_OAUTH_CLIENT_SECRET=<client secret>
   GOOGLE_OAUTH_REFRESH_TOKEN=<nilai langkah 4>
   GOOGLE_DRIVE_FOLDER_ID=<folder id langkah 5>
   ```
   Di Render: sama di Dashboard Environment.

Verifikasi: `/health` → `"drive": true`; kirim foto → balasan ada tautan "Bukti transfer" dan baris Sheet punya isi `Link Bukti`.

Catatan: unggahan hanya terjadi untuk baris **baru** (duplikat dilewati), dan hanya bila ekstraksi/simpan Sheet sukses. Gagal unggah Drive tidak mematikan proses — kolom dibiarkan kosong, error muncul di log. Refresh token tidak kedaluwarsa selama tidak dicabut (atau password Gmail diganti).

## Alur

- Kirim **foto ke bot dalam satu pesan**, dengan caption (opsional, mis. `Rp195.000 penjualan satvika`). Caption dipakai sebagai konteks ekstraksi **dan** disimpan utuh di kolom `Caption`.
  - Caption yang dikirim sebagai pesan terpisah **tidak** terbaca bot — selalu satu paket foto + caption.
- Mode vision (AI): gambar + caption dikirim bersama ke AI → field diisi AI.
- Mode mock (tanpa AI): gambar tidak dibaca; tanggal dari nama file, nominal/arah dari caption, keterangan = caption.
- Bot ekstrak → append ke Sheet (13 kolom), upload foto ke Drive + tautan di kolom `Link Bukti`, balasan status (termasuk link bukti). Duplikat (Ref ID sama) dilewati.
- Sheets gagal → antre `pending.jsonl`, retry otomatis tiap siklus polling.
- Review: ubah kolom `Status` `draft` → `verified` setelah dicek. **Angka AI belum dipakai sebelum verified.**

## Skema Sheet (13 kolom)

`Tanggal | Keterangan | Nominal | Arah | Kategori | Status | Sumber File | Ref ID | Confidence | Tanggal Input | Catatan | Caption | Link Bukti`

- Header dibuat otomatis saat Sheet kosong; Sheet lama (11/12 kolom) otomatis ditambah kolom yang kurang.
- `Keterangan` = hasil ekstraksi AI (atau caption di mode mock); `Caption` = teks asli apa adanya; `Link Bukti` = tautan foto di Google Drive (kosong bila fitur Drive mati/gagal).

## Endpoint

- `GET /health` — status telegram/sheets/ai/drive + antrean.
- `POST /api/extract` `{filename, image_base64?, caption?}` — ekstraksi + append tanpa bot (untuk uji cepat/web nanti).

## Antrean Gagal (`pending.jsonl`)

Mekanisme agar ekstraksi tidak hilang ketika Google Sheets tidak bisa dijangkau:

1. **Kapan masuk antrean** — `append_sheet()` gagal (Sheets down, permission salah, kredensial kedaluwarsa, koneksi putus) setelah ekstraksi sukses. Record ditulis ke `pending.jsonl` (1 baris JSON per kejadian) lalu pengguna tetap diberi balasan bahwa ekstraksi berhasil tapi pengiriman ditunda.
2. **Format baris** — hasil ekstraksi lengkap (`tanggal`, `keterangan`, `nominal`, `ref_id`, `caption`, dst.) + `_error` (pesan kegagalan) + `_ts` (epoch).
3. **Kapan dikirim ulang** — `flush_pending()` dipanggil **tiap siklus polling** sebelum `getUpdates` berikutnya. Tiap baris dihapus dari file dulu, lalu dicoba append; gagal lagi → ditulis ulang. Sukses/duplikat → baris hilang dari antrean.
4. **Tidak pernah menggandakan** — retry melewati cek dedupe `Ref ID` yang sama seperti proses normal, jadi meski baris sempat terkirim sebelum error, retry akan berstatus `dup`.
5. **Batas** — file di filesystem proses; **hilang saat redeploy Render** (tidak persisten). Antrean ini penahan kegagalan sementara, bukan penyimpanan. `GET /health` menampilkan `pending: true/false`.

`pending.jsonl` sudah masuk `.gitignore` — tidak pernah ikut ter-commit.

## Batasan (milestone 1)

- Ekstraksi mock tanpa AI = nominal hanya dari caption (gambar tidak dibaca); tanpa caption, kolom `Nominal` kosong.
- Klasifikasi awal kosong (kolom Kategori diisi AI bila vision aktif, sisanya manual).
- Belum ada balancing (milestone 2) dan tanya-jawab (milestone 3).

## Pengembangan Berikutnya

Urutkan berdasarkan nilai buat brief (3 pilihan kelompok) dan usaha:

1. **Balancing (inti Pilihan 1)** — baca mutasi bank (PDF/XLSX) → cocokkan baris Sheet via Ref ID/tanggal+nominal → status `cocok` / `belum cocok` / `tercatat di kas tapi tidak di mutasi` + laporan selisih per periode.
2. **Web app baru (rekap/PnL)** — bangun dari awal, membaca Sheet yang sama via service account → rekap harian + draf PnL dari data bot.
3. **Tanya-jawab & ringkasan (Pilihan 3)** — command bot (`/total Januari`) → query kode → angka dari kode, LLM hanya merangkai kalimat, jawaban wajib menunjuk baris sumber. Rancangan lengkapnya di bagian **Rancangan Tanya-Jawab & Data**.
4. **Kualitas** — pytest (extract/dedupe/pending), eval 10 foto sampel → bahan EV-xx Testing Report.
5. **Integrasi lanjutan bila waktu cukup** — klasifikasi kategori otomatis (rule/Jev), command `/rekap`, ekstraksi invoice PDF, multi-kas, deploy always-on.

Yang tidak perlu dibangun: database, login, dashboard analytics, n8n.

## Rancangan Tanya-Jawab & Data (hasil diskusi desain)

Keputusan inti: **tanpa database untuk query AI** — Sheet tetap satu-satunya source of truth.

### Query AI baca Sheet langsung, bukan mirror DB

Data diedit manual di Sheet (draft → verified); mirror DB akan jadi basi dan menimbulkan masalah sync yang justru dihindari. Volume kecil → baca via `gspread` saat query juga cukup. Bentuknya **tools**, bukan database:

| Tool | Fungsi |
|---|---|
| `aggregate(period, arah, kategori?)` | total masuk/keluar — dihitung **kode** |
| `list_rows(period, filter?)` | daftar baris untuk pertanyaan rinci |
| `get_receipt(ref_id)` | ambil `Link Bukti` dari Drive (read-only) |

Aturan tetap: AI hanya menerjemahkan intent → parameter dan menyusun narasi; jawaban wajib menyebut sumber (tab/baris).

### PnL & reconcile: cukup spreadsheet

- **PnL**: baca → agregasi per kategori di kode (sudah dibuktikan prototipe).
- **Reconcile**: matching *in-memory* antara transaksi Sheet dan **tab `Mutasi`** (hasil parse PDF/XLSX disimpan sekali — jangan parse ulang tiap run) → hasil ditulis ke kolom (`Status Reconcile`, `Cocok Dengan`, `Selisih`) + laporan selisih per periode.
- **Database hanya kalau**: butuh log nilai AI vs final (sebelum koreksi vs setelah verifikasi) untuk mengukur akurasi — bahan SC-01/SC-02 & Testing Report — dengan **SQLite** append-only, atau baris > ~100rb / multi-penulis → **PostgreSQL**. Sinkron **satu arah Sheet → DB**, tidak pernah dua arah.

### Routing pesan: foto vs tanya-data

- Foto/dokumen → jalur ekstraksi **tidak berubah** dan tidak pernah melewati LLM (cukup cek tipe pesan).
- Teks → berurutan: (1) command `/` dulu (gratis, deterministik); (2) bahasa bebas → **satu panggilan LLM tool-calling** — pilihan tool-nya *adalah* routing-nya. Classifier terpisah tidak direkomendasikan (berarti dua panggilan AI per pertanyaan: lambat, mahal, dua titik gagal).
- Klasifikasi gagal / AI mati → balasan bantuan (fallback, pola sama dengan mode mock).

### Command `/` — opsional, parameter divalidasi

- Tidak wajib; disarankan untuk pola berulang: `/total Nov`, `/rekap`, `/help`.
- Parameter tidak valid → balas **usage singkat dengan contoh**, tidak pernah exception:
  - `/total` atau `/total abc` → `Format: /total <bulan> — contoh: /total Nov, /total 2026-11`
  - command tidak dikenal → ringkasan bantuan.
- `first = text.split()[0].split("@")[0]` (buang `@botname` di grup) → lookup dict handler → parse argumen di dalam handler.

### Catatan desain (belum diimplementasi)

- **Balasan ack "sedang diproses"** — saat ini foto yang diproses tidak dibalas sampai selesai (ekstraksi bisa 10–60 detik, user menunggu tanpa kabar). Rencana: kirim `⏳ Diterima, sedang diproses…` segera setelah lolos whitelist, **sebelum** unduh file/ekstraksi, lalu pesan hasil seperti sekarang (✅/♻️/⚠️/❌). Kegagalan kirim ack diabaikan agar tidak mematikan proses. Pertimbangan UX: menurunkan risiko user kirim ulang karena mengira gagal, dan memenuhi UN-01 (kepastian transaksi diterima). Bentuk sederhana: dua bubble terpisah; opsi lanjut: edit pesan ack menjadi hasil akhir.
- **Ref ID prioritas nomor referensi dokumen** — `Ref ID` saat ini selalu diisi `tg:<file_unique_id>` sehingga nomor referensi hasil ekstraksi (`rec["ref"]`) terbuang. Rencana: `ref_id = f"doc:{rec['ref']}"` bila ada, fallback `tg:<file_unique_id>`. Alasan: nomor referensi bank unik per transaksi → deteksi duplikat lebih kuat (foto diedit/kompresi ulang tetap ketangkap) dan menjadi kunci pencocokan untuk balancing (milestone 2) terhadap kolom referensi di mutasi bank. Format prefix `doc:`/`tg:` ditentukan sejak awal dan tidak diubah-ubah.
- **Google Drive sebagai penyimpanan bukti transfer** — sudah diimplementasikan (lihat "Setup Google Drive"): 1 folder tujuan + kolom `Link Bukti`. Yang belum: **folder per periode** (`Receipts 2026/01`) supaya arsip terpisah per bulan.
- **Nama admin otomatis** — tambah kolom `Nama Admin` diisi dari data pengirim Telegram (`message.from`: `first_name` + `last_name`, fallback `username`, terakhir `"Tidak diketahui"`) — menggantikan kolom "Tanggal Input dan Nama Admin" gaya Cash Report perusahaan. Pertimbangan: nama bergantung pada akun pengirim (bukan selalu orang yang sama dengan yang menginput).
- **Multi-sheet per periode** — Sheet Tujuan ditentukan dari tanggal ekstraksi (`YYYY-MM` → sheet/bulan). Sebelum append: cek apakah sheet periode ada.
  - Ada → pakai.
  - Belum ada → **buat sheet baru otomatis** (`add_worksheet("Nov 2026")` + header), atau fallback ke sheet umum + kolom `Periode` bila otomatis dinilai berisiko.
  - Dedupe Ref ID wajib **per sheet** (col_values dibaca dari sheet tujuan, bukan sheet pertama).
  - Alternatif sederhana: 1 spreadsheet berisi banyak tab bulanan (bukan banyak file) — disarankan, karena share service account cukup 1 kali.
