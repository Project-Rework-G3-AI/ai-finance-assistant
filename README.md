# Bot Pencatatan Transaksi — Milestone 1: Telegram → Ekstraksi → Cash Report

Bot Telegram terima foto/screenshot bukti transaksi → ekstraksi field → tulis ke **Cash Report** (satu file gabungan per tahun, flat ledger `TRANSAKSI`, RECAP/PnL otomatis, status `draft`, review manual). Tanpa database.

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

    BOT -->|"Ref ID (kolom I) duplikat?"| DUP{"sudah<br/>ada?"}
    DUP -->|"ya"| SKIP["balasan: dilewati"]
    DUP -->|"tidak"| CR[("Cash Report {tahun}<br/>sheet TRANSAKSI<br/>(cloud, SA)")]

    CR -->|"cari/copy template"| YR["Folder tahun +<br/>file Cash Report {tahun}<br/>(Drive OAuth)"]
    CR -->|"upload foto baru<br/>(opsional)"| DRIVE["Google Drive<br/>Receipts · kolom Link Bukti"]
    CR -->|"gagal"| PEND["pending.jsonl<br/>(lokal)"]
    PEND -->|"retry tiap siklus"| CR

    CR -->|"review manual:<br/>draft → verified"| U
    W["Browser lokal<br/>GET /health<br/>POST /api/extract"] --> BOT

    classDef cloud fill:#1e3a5f,stroke:#3b82f6,color:#fff
    classDef local fill:#14532d,stroke:#22c55e,color:#fff
    class TG,CR,VIS,DRIVE,YR cloud
    class BOT,MOCK,PEND,W local
```

- Satu proses di lokal: polling Telegram + endpoint API berjalan bersamaan; semua koneksi **keluar** (internet), tanpa server publik.
- Mode vision (AI) dipakai bila `AI_API_KEY` ada; selalu fallback ke mock agar alur tidak pernah putus.
- **Split kredensial**: Drive (cari folder, copy template, upload foto) = OAuth user; sel/tab Cash Report = service account. `pending.jsonl` = penahan gagal, bukan penyimpanan utama.

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
7. **Siapkan folder Cash Report & share ke SA** — buat folder `Cash Report` di Drive → **Share** → tempel email service account (langkah 6) → role **Editor** → centang "Don't send". *(Semua file yang kelak dibuat di dalamnya — folder tahun, file laporan tahunan — mewarisi izin ini.)*
8. **Isi `.env`**:
   ```
   GOOGLE_SERVICE_ACCOUNT_FILE=service_account.json
   CASH_REPORT_FOLDER_ID=<ID folder Cash Report>
   CASH_REPORT_TEMPLATE_ID=<ID spreadsheet template>
   ```

Verifikasi: `curl http://127.0.0.1:8000/health` → `"sheets": true`.

Troubleshooting: append gagal "insufficient permissions" = email service account (langkah 6) belum dapat akses Editor di folder (langkah 7).

Opsional AI: isi `AI_API_KEY` (+ `AI_BASE_URL`/`AI_MODEL` bila pakai provider lain) untuk ekstraksi vision. Tanpa itu = mode mock (tanggal dari nama file, nominal dari caption).

## Setup Cash Report (folder, template, verifikasi)

Struktur yang dipakai bot:

```
Google Drive/
├── Cash Report/
│   ├── TEMPLATE/
│   │   └── Cash Report TEMPLATE      ← CASH_REPORT_TEMPLATE_ID (dibuat build_template.py)
│   └── <tahun>/                      ← otomatis (folder tahun)
│       └── Cash Report <tahun>       ← otomatis (copy template, mis. "Cash Report 2026")
└── Receipts/                         ← GOOGLE_DRIVE_FOLDER_ID (upload foto)
```

**Template dibangun oleh kode** (gaya Bizschool — tidak perlu membuat manual):

```bash
python cash_report/build_template.py   # sekali jalan -> print id spreadsheet
python cash_report/verify_template.py  # read-only: struktur + formula
```

Isi template (7 sheet, year-agnostic):

| Sheet | Isi |
|---|---|
| SETUP | daftar kantong (BRI, BNI, Jago, UANG KAS) & kategori — master buat AI. Daftar kategori bersumber dari `cash_report/categories.py`, lihat `cash_report/KATEGORI.md` |
| ACCOUNT | saldo awal per kantong (input manual) + Masuk/Keluar (SUMIFS) |
| TRANSAKSI | **flat ledger** — satu-satunya sheet yang ditulis bot |
| RECAP OVERVIEW | rentang periode + pendapatan/pengeluaran/selisih per kategori (SUMIFS, transfer dikecualikan) |
| YEARLY OVERVIEW | arus kas 12 bulan (SUMIFS per bulan) |
| EXPENSE DETAIL | pengeluaran per kategori per bulan + memo COGS (input manual, opsional) |
| INCOME STATEMENT | laba rugi per bulan — turunan RECAP/EXPENSE (SUMIFS) |

Sel periode (`RECAP OVERVIEW!B3`) ditulis bot saat file baru dibuat = `1 Januari <tahun>`; semua sheet lain turunannya.

Aturan penting:

- **Transfer antar kantong** ditulis **2 baris berpasangan** — keduanya berbagi `Ref ID` yang sama di kolom I (pasangan dikenali dari situ) — saldo tiap kantong akurat, recap/PnL mengecualikannya.
- `Saldo Awal` di ACCOUNT diisi manual sekali per tahun.
- Kolom **Link Bukti (K)** diisi otomatis saat foto terupload ke `Receipts`.

## Setup Google Drive (opsional — arsip bukti transfer)

Foto yang diterima juga diunggah ke Google Drive (folder `Receipts`); tautannya ditulis ke kolom **Link Bukti (K)** supaya bisa dibuka langsung dari Cash Report (memenuhi UC-02). Fitur ini **opsional** — tanpa konfigurasi, bot tetap jalan normal.

Upload & manajemen file memakai **OAuth akun user** (bukan service account): Google memblokir service account membuat file sendiri (error `storageQuotaExceeded`). Scope yang dipakai **`https://www.googleapis.com/auth/drive`** (penuh) — diperlukan untuk mencari folder tahun dan menyalin template milik user. **Token lama ber-scopes `drive.file` tidak berlaku untuk fitur ini — buat ulang refresh token (langkah 4).**

1. **Aktifkan Drive API** — Google Cloud Console → **APIs & Services** → **Library** → cari "Google Drive API" → **Enable**.
2. **OAuth consent screen** — **APIs & Services** → **OAuth consent screen** → User Type **External** → isi app name/email → **Save** → tab **Audience/Testing** → **+ Add users** → tambahkan Gmail yang akan jadi pemilik foto (mode Testing cukup, tidak perlu verifikasi Google).
3. **Buat OAuth client** — **Credentials** → **Create Credentials** → **OAuth client ID** → Application type **Desktop app** → Create → **Download JSON** → simpan sebagai `credentials.json` di folder `bot/` (sudah masuk `.gitignore`).
4. **Ambil refresh token (sekali saja)** — jalankan:

```bash
python oauth_init.py
```

   Browser terbuka → login Gmail tujuan → izinkan → salin baris `GOOGLE_OAUTH_REFRESH_TOKEN=...` dari terminal.
5. **Buat folder tujuan** — di Drive akun yang sama, mis. `Receipts 2026` → salin **Folder ID** dari URL `drive.google.com/drive/folders/`**`ID`**. *(Tidak perlu share — file nanti milik akun ini.)*
6. **Isi `.env`**:
   ```
   GOOGLE_OAUTH_CLIENT_ID=<client id dari langkah 3>
   GOOGLE_OAUTH_CLIENT_SECRET=<client secret>
   GOOGLE_OAUTH_REFRESH_TOKEN=<nilai langkah 4>
   GOOGLE_DRIVE_FOLDER_ID=<folder id langkah 5>
   ```
   Di Render: sama di Dashboard Environment.

Verifikasi: `/health` → `"drive": true`; kirim foto → balasan ada tautan "Bukti transfer" dan baris Cash Report punya isi kolom Link Bukti.

Catatan: unggahan hanya terjadi untuk baris **baru** (duplikat dilewati), dan hanya bila tulis Cash Report sukses. Gagal unggah Drive tidak mematikan proses — kolom dibiarkan kosong, error muncul di log. Refresh token tidak kedaluwarsa selama tidak dicabut (atau password Gmail diganti).

## Alur

- Kirim **foto ke bot dalam satu pesan**, dengan caption (opsional, mis. `Rp195.000 penjualan satvika`). Caption dipakai sebagai konteks ekstraksi **dan digabung ke Keterangan** (`hasil LLM — caption`, bila keduanya berbeda).
  - Caption yang dikirim sebagai pesan terpisah **tidak** terbaca bot — selalu satu paket foto + caption.
- Mode vision (AI): gambar + caption dikirim bersama ke AI → field diisi AI (`bank` = **kantong asal** BRI/BNI/Jago/TUNAI; transfer menghasilkan `arah=transfer` + `kantong_tujuan`; kosong → `CR_DEFAULT_BANK`).
- Mode mock (tanpa AI): gambar tidak dibaca; tanggal dari nama file, nominal/arah dari caption, keterangan = caption.
- Bot ekstrak → **pipeline Cash Report**: folder tahun (buat bila perlu) → file `Cash Report <tahun>` (copy template bila baru + tulis sel periode) → sheet `TRANSAKSI` → cek duplikat (Ref ID, kolom I) → upload foto ke Receipts → tulis baris A–K (transfer = 2 baris berpasangan, Ref ID sama) → balasan status + tautan bukti.
- Sheet `TRANSAKSI` tidak ada (template salah) atau tulis gagal → antre `pending.jsonl`, retry otomatis tiap siklus polling.
- Review: ubah kolom `Status` (G) `draft` → `verified` setelah dicek. **Angka AI belum dipakai sebelum verified.**

## Skema kolom sheet TRANSAKSI (A–K)

Flat ledger — baris 1 header, data mulai baris 2, append di baris pertama kolom A kosong:

| Kolom | Isi | Aturan |
|---|---|---|
| A Tanggal | tanggal transaksi | format tampilan `d-mmm-yy` (format bawaan sel) |
| B Kantong | BRI / BNI / Jago / UANG KAS | dari ekstraksi (`bank`), fallback `CR_DEFAULT_BANK` |
| C Masuk | nominal | terisi bila arah = masuk (atau sisi tujuan transfer) |
| D Keluar | nominal | terisi bila arah = keluar (atau sisi asal transfer) |
| E Kategori | daftar di sheet SETUP (sumber: `cash_report/categories.py`) | dari ekstraksi, dinormalkan ke nama baku; reviewer boleh koreksi |
| F Keterangan | hasil ekstraksi LLM, caption digabung dengan ` — ` bila berbeda | reviewer boleh rapikan |
| G Status | `draft` saat tulis; reviewer → `verified` | |
| H Catatan | catatan sistem (bukan LLM): "wajib ditinjau", nilai tidak terbaca, anomali | |
| I Ref ID | dedupe (`tg:…` / `manual:…`) | pasangan transfer memakai Ref ID sama |
| J Sumber File | nama file foto asli dari Telegram | |
| K Link Bukti | tautan foto di Drive (kosong bila fitur off/gagal) | |

- **Transfer antar kantong**: `arah=transfer` + `kantong_tujuan` → bot menulis **2 baris** (asal di D, tujuan di C) dengan **Ref ID (I) sama** — itulah penanda pasangannya; RECAP/PnL mengecualikan kategori `Transfer Antar Bank`, ACCOUNT tetap menghitungnya (saldo per kantong benar).
- **Catatan diisi kode, bukan LLM** — contoh: `Ekstraksi AI — wajib ditinjau… (nominal tidak terbaca — isi manual)`, `Mock ekstraksi:…`, `[… transfer tanpa kantong tujuan terbaca …]`.
- Query PnL/reconcile nanti **hanya menghitung baris `Status = verified`** dan memakai C/D sebagai angka.

## Endpoint

- `GET /health` — status telegram/sheets/ai/drive + antrean.
- `POST /api/extract` `{filename, image_base64?, caption?}` — ekstraksi + tulis Cash Report tanpa bot (untuk uji cepat/web nanti).

## Antrean Gagal (`pending.jsonl`)

Mekanisme agar ekstraksi tidak hilang ketika Drive/Sheets tidak bisa dijangkau:

1. **Kapan masuk antrean** — `write_cash_report()` gagal (folder/template tidak ada, permission salah, kredensial kedaluwarsa, koneksi putus) setelah ekstraksi sukses. Record ditulis ke `pending.jsonl` (1 baris JSON per kejadian) lalu pengguna tetap diberi balasan bahwa ekstraksi berhasil tapi pengiriman ditunda.
2. **Format baris** — hasil ekstraksi lengkap (`tanggal`, `keterangan`, `nominal`, `arah`, `bank`, `ref_id`, `catatan`, dst.) + `_error` (pesan kegagalan) + `_ts` (epoch).
3. **Kapan dikirim ulang** — `flush_pending()` dipanggil **tiap siklus polling** sebelum `getUpdates` berikutnya. Tiap baris dihapus dari file dulu, lalu dicoba tulis; gagal lagi → ditulis ulang. Sukses/duplikat → baris hilang dari antrean.
4. **Tidak pernah menggandakan** — retry melewati cek dedupe `Ref ID` (kolom I) yang sama seperti proses normal, jadi meski baris sempat terkirim sebelum error, retry akan berstatus `dup`. Retry **tanpa gambar** (file foto tidak ikut antrean) → kolom Link Bukti kosong — cukup isi manual atau kirim ulang foto untuk baris yang belum ada.
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
| `get_receipt(ref_id)` | ambil tautan foto dari kolom Link Bukti (K) (read-only) |

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
- **Google Drive sebagai penyimpanan bukti transfer** — sudah diimplementasikan (lihat "Setup Google Drive"): folder `Receipts` + kolom Link Bukti (K). Yang belum: **folder per periode** (`Receipts 2026/01`) supaya arsip terpisah per bulan.
- **Nama admin otomatis** — tambah kolom `Nama Admin` diisi dari data pengirim Telegram (`message.from`: `first_name` + `last_name`, fallback `username`, terakhir `"Tidak diketahui"`) — menggantikan kolom "Tanggal Input dan Nama Admin" gaya Cash Report perusahaan. Pertimbangan: nama bergantung pada akun pengirim (bukan selalu orang yang sama dengan yang menginput).
- **Struktur lama (sudah pensiun)** — sebelum gaya Bizschool, bot menulis ke file per bank per tahun dengan tab bulanan + kolom A–P format perusahaan. Struktur itu digantikan file gabungan `Cash Report <tahun>` / sheet `TRANSAKSI` (lihat "Skema kolom"); file lama dibiarkan sebagai arsip historis.
