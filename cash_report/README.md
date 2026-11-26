# Cash Report Automation

> **[DEPRECATED]** Dokumen ini menjelaskan prototipe awal (`cr.py`) yang memakai
> OAuth user — jalur tersebut sudah diganti Apps Script Web App (lihat
> `apps_script/Code.gs` dan README utama bagian Drive). Kredensial `OAUTH_*`
> di bawah tidak berlaku lagi. Referensi aktif: README utama di root `bot/`.

Dokumentasi singkat mengenai struktur folder Google Drive, alur input
data ke fungsi spreadsheet, dan kredensial Google API yang dibutuhkan.

## 1. Struktur Folder Google Drive

Script menggunakan struktur folder Google Drive berikut:

``` text
Google Drive/
├── Cash Report/
│   ├── Spreadsheet Template Cash Report
│   └── 2026/
│       ├── Cash Report - BNI 2026
│       ├── Cash Report - BCA 2026
│       └── ... (file cash report per bank)
│
└── Receipts/
    ├── receipt_17.jpg
    ├── receipt_22.png
    └── ... (file bukti transaksi)
```

Keterangan:

-   **Cash Report** merupakan folder utama untuk menyimpan template dan
    spreadsheet laporan kas.
-   **Spreadsheet Template Cash Report** merupakan file template yang
    digunakan sebagai dasar pembuatan cash report.
-   **Folder tahun** (contoh: `2026`) digunakan untuk menyimpan
    spreadsheet cash report pada tahun tersebut.
-   **File cash report** dibuat terpisah berdasarkan bank.
-   **Receipts** digunakan untuk menyimpan gambar bukti transaksi yang
    diunggah melalui Telegram.

### Pembuatan Folder dan Spreadsheet Otomatis

Folder tahun dan file spreadsheet cash report akan dibuat secara
otomatis oleh script apabila belum tersedia file atau folder yang
sesuai.

Script menentukan kebutuhan folder dan spreadsheet berdasarkan informasi
transaksi yang diekstrak dari receipt, terutama tahun transaksi dan bank
yang digunakan. Jika folder tahun atau cash report untuk bank terkait
belum tersedia, script akan membuatnya berdasarkan spreadsheet template.

## 2. Input untuk Fungsi Spreadsheet

Alur pemrosesan dimulai dari fungsi `save_and_record_receipt`.

Setelah gambar receipt diproses menggunakan OCR/LLM API untuk
mengekstrak informasi transaksi, `save_and_record_receipt` akan
meneruskan hasil ekstraksi ke fungsi-fungsi spreadsheet.

Parameter yang dibutuhkan:

  -----------------------------------------------------------------------
  Parameter                           Keterangan
  ----------------------------------- -----------------------------------
  `image_bytes`                       Data bytes gambar receipt yang akan
                                      diunggah ke Google Drive.

  `filename`                          Nama file receipt yang akan
                                      disimpan di Google Drive.

  `mime_type`                         MIME type gambar, misalnya
                                      `image/jpeg`, `image/png`, atau
                                      `image/webp`.

  `result`                            Dictionary berisi hasil ekstraksi
                                      informasi transaksi dari OCR/LLM
                                      API.

  `telegram_caption`                  Caption yang disertakan pengguna
                                      saat mengunggah gambar melalui
                                      Telegram.
  -----------------------------------------------------------------------

### Contoh `result`

``` python
{
    'is_transfer_receipt': True,
    'transfer_amount_idr': 800353,
    'transfer_fee_idr': 0,
    'total_debited_idr': 800353,
    'sender_name': 'Prabskuy',
    'recipient_name': 'Jokovich',
    'transaction_bank': 'BNI',
    'sender_bank': 'BNI',
    'recipient_bank': 'BNI',
    'transaction_detail': 'Tepung beras dan giling jagung',
    'category': 'Bahan Baku',
    'transaction_datetime': '2026-01-01T16:28:32',
    'reference_number': None,
    'telegram_caption': 'Pembelian bahan baku'
}
```

### Penjelasan Key pada `result`

  ------------------------------------------------------------------------
  Key                      Tipe                    Keterangan
  ------------------------ ----------------------- -----------------------
  `is_transfer_receipt`    `bool`                  Menunjukkan apakah
                                                   gambar merupakan bukti
                                                   transfer yang valid
                                                   atau bukan.

  `transfer_amount_idr`    `int`                   Jumlah bersih yang
                                                   ditransfer kepada
                                                   penerima.

  `transfer_fee_idr`       `int`                   Biaya administrasi atau
                                                   biaya transfer.

  `total_debited_idr`      `int`                   Total dana yang didebit
                                                   dari rekening, termasuk
                                                   biaya transfer jika
                                                   ada.

  `sender_name`            `str`                   Nama pengirim dana.

  `recipient_name`         `str`                   Nama penerima dana.

  `transaction_bank`       `str`                   Bank yang digunakan
                                                   untuk melakukan
                                                   transaksi.

  `sender_bank`            `str`                   Bank asal atau bank
                                                   pengirim.

  `recipient_bank`         `str`                   Bank tujuan atau bank
                                                   penerima.

  `transaction_detail`     `str`                   Keterangan atau tujuan
                                                   transaksi berdasarkan
                                                   hasil ekstraksi AI.

  `category`               `str`                   Kategori transaksi yang
                                                   diusulkan AI.
                                                   Pengategorian
                                                   diutamakan berdasarkan
                                                   `telegram_caption`.
                                                   Jika caption tidak
                                                   tersedia atau tidak
                                                   cukup informatif,
                                                   gunakan
                                                   `transaction_detail`
                                                   sebagai dasar
                                                   kategorisasi.

  `transaction_datetime`   `str`                   Tanggal dan waktu
                                                   transaksi dilakukan,
                                                   menggunakan format
                                                   datetime ISO 8601.

  `reference_number`       `str`                   Nomor referensi
                                                   transaksi jika tersedia
                                                   pada receipt.

  `telegram_caption`       `str`                   Caption yang diberikan
                                                   pengguna ketika
                                                   mengunggah gambar
                                                   receipt melalui
                                                   Telegram.
  ------------------------------------------------------------------------

## 3. Credentials dan Google API Services

Fungsi spreadsheet membutuhkan dua service object:

-   `sheets_service` --- digunakan untuk membaca, membuat, dan mengubah
    spreadsheet melalui Google Sheets API.
-   `drive_service` --- digunakan untuk mengelola file dan folder di
    Google Drive, termasuk mengunggah receipt serta membuat folder atau
    spreadsheet yang diperlukan.

Kedua service tersebut diperoleh melalui OAuth pada fungsi
`get_google_services`.

### Environment Variables

Sebelum menjalankan script, isi environment variables berikut:

``` env
OAUTH_CLIENT_ID=your_oauth_client_id
OAUTH_CLIENT_SECRET=your_oauth_client_secret
OAUTH_REFRESH_TOKEN=your_oauth_refresh_token
```
