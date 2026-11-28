# Hasil evaluasi SC-05: bukti transaksi berulang tidak mencatat ganda

Dokumen ini melaporkan hasil pengukuran kriteria keberhasilan SC-05 pada bot
pencatatan transaksi PT Lokal Komoditi Indonesia, Kelompok G3.

## Apa yang diukur

Berapa baris yang tersimpan ketika berkas bukti transaksi yang sama dikirim
lebih dari sekali. Satu kiriman berulang harus tetap menghasilkan **satu baris**.

Bukan isi, bukan waktu, bukan biaya. Kriteria ini mengukur **tidak adanya baris
ganda**.

## Target

**Seluruh duplikat ditolak.** Dikutip dari tabel Success Criteria pada BRD
bagian 6.

## Hasil

| Skenario | Kiriman | Baris tersimpan | Duplikat ditolak | Harapan | |
|---|---|---|---|---|---|
| Kirim ulang berkas yang sama | 10 | 5 | **5 dari 5** | ditolak | sesuai |
| Isi sama, `file_id` berbeda | 10 | 10 | **0 dari 5** | ditolak | **tidak sesuai** |
| Gambar berbeda (kendali) | 5 | 5 | — | dicatat | sesuai |

**Status: TERCAPAI.** Lima dari lima berkas duplikat ditolak, dan kendali tetap
tercatat.

Angka yang dinilai adalah **5 dari 5**, bukan "satu dari satu". Lima gambar
berbeda masing-masing dikirim dua kali, sehingga penyebutnya punya arti.

## Tiruan harus mengikuti produksi

Harness ini memanggil `handle_update` dan `write_cash_report` yang asli, jadi
tiruan worksheet-nya harus punya **semua** metode yang dipanggil produksi.

Pernah gagal di sini. Produksi menambahkan `ws.format(...)` untuk menyeragamkan
format kolom Tanggal. Tiruan belum punya metodenya, sehingga seluruh penulisan
gagal dengan `AttributeError`. Yang terjadi kemudian justru lebih berbahaya:
`handle_update` menangkap kegagalan itu dan menaruh transaksinya di antrean
gagal, bukan melempar exception. Harness melihat nol baris tersimpan dan
membacanya sebagai "duplikat ditolak" — laporan berbunyi **TERCAPAI** padahal
tidak ada satu pun baris yang tersimpan.

Dua penjaga sekarang ada di tempatnya:

1. `test_fake_worksheet_supports_every_method_production_calls` membandingkan
   metode yang dipanggil `write_cash_report` dengan yang disediakan tiruan.
2. Harness memeriksa antrean gagal sebelum dan sesudah tiap skenario. Bila ada
   transaksi masuk antrean, kasus itu ditandai gagal diukur, angkanya tidak
   dihitung, dan statusnya **GAGAL DIUKUR** — bukan TERCAPAI.

## Kendali, dan kenapa itu wajib

Skenario ketiga mengirim lima gambar **berbeda**, masing-masing sekali. Semuanya
harus tercatat.

Tanpa kendali ini, aplikasi yang menolak **semua** kiriman akan tampak lulus
sempurna: setiap duplikat "ditolak" karena semuanya ditolak. Kendali inilah yang
membedakan dedup yang benar dari dedup yang terlalu agresif.

Kendali lulus: 5 kiriman menghasilkan 5 baris.

## Temuan: dedup tidak memakai hash

BRD menyebutkan di ruang lingkup:

> *"Pemeriksaan duplikat berbasis hash berkas sebelum pemrosesan."*

Dan di UC-03:

> *"Sistem mengenali berkas identik melalui hash."*

Kenyataannya tidak ada hash sama sekali di kode:

```
grep -niE "hashlib|sha256|md5" main.py
  (kosong)
```

Dedup hanya memakai `ref_id` yang dibentuk dari identitas berkas Telegram:

| Jalur | `ref_id` |
|---|---|
| Telegram | `tg:{file_id}` |
| API | `manual:{nama_berkas}` |

Akibatnya terlihat pada skenario kedua: **isi gambar yang sama dengan `file_id`
berbeda menghasilkan dua baris.** Nol dari lima ditolak.

Ini bukan kegagalan yang bisa diperbaiki tanpa mengubah produksi, jadi
dilaporkan sebagai **temuan**, tidak dipakai menghukum kriteria. Yang dinilai
tetap kasus wajib, sesuai permintaan: berkas yang sama diunggah ulang lewat
Telegram tidak boleh membuat transaksi dobel.

Temuan ini sudah tercatat sebagai BUG-02 pada draft Testing Evaluation Report:

> *"`ref_id` pada jalur API diambil dari nama berkas, bukan isi berkas. Dua
> transaksi berbeda dengan nama berkas sama dianggap duplikat sehingga transaksi
> sah hilang. Sebaliknya berkas sama dengan nama berbeda lolos menjadi dua
> baris."*

## Cara mengukur

```bash
python3 tests/sc_runner.py --sc05
```

Gratis. Tidak butuh kunci AI, Google Sheets, dataset, atau jaringan. Selesai di
bawah satu detik.

### Yang dipanggil apa adanya

`handle_update` dan `write_cash_report` dari `main.py` dijalankan tanpa disalin.
Logika dedup, urutan pemeriksaan, dan cara `ref_id` dibentuk semuanya yang asli.

### Yang diganti, dan alasannya

| Bagian | Diganti | Alasan |
|---|---|---|
| Telegram | tiruan | Tidak ada bot token di mesin ini |
| Google Sheets | worksheet tiruan | Dedup hanya membaca kolom Ref ID lalu menambah baris |
| Ekstraksi AI | jawaban tetap | SC-05 menguji dedup, bukan mutu pembacaan gambar |

Worksheet tiruan meniru dua perilaku Google Sheets yang relevan: `col_values`
memangkas sel kosong di ujung, dan `update` menulis pada rentang A:K.

## Bukti harness bisa merah

Angka "lima dari lima" hanya berarti bila harness-nya bisa gagal. Karena itu ada
test yang mematikan pemeriksaan Ref ID lalu memastikan hasilnya berubah:

| Keadaan | Hasil |
|---|---|
| Dedup aktif | 5 dari 5 ditolak, **TERCAPAI** |
| Dedup dimatikan | 0 dari 5 ditolak, **BELUM TERCAPAI** |

Tanpa pembuktian ini, hijau pada harness tidak bisa dibedakan dari harness yang
selalu hijau.

## Batas pengukuran

1. **Bukan Telegram sungguhan.** Tidak ada bot token di mesin ini. Yang diuji
   adalah jalur kode yang dijalankan Telegram, bukan Telegram itu sendiri.
2. **Bukan Google Sheets sungguhan.** Worksheet tiruan meniru `col_values` dan
   `update`. Perilaku Sheets yang tidak dipakai `write_cash_report` tidak ditiru.
3. **Ekstraksi tidak diuji.** Jawaban model diganti tetap supaya hasilnya tidak
   bergantung pada isi gambar.
4. **Lima gambar, bukan 118.** Dedup tidak bergantung pada isi gambar, jadi lima
   cukup untuk membuktikan perilakunya. Menambah gambar tidak menambah bukti.
5. **Satu kali jalan.** Dedup tidak acak, jadi hasilnya tidak bervariasi
   antar-run seperti SC-01.

## Berkas

| Berkas | Isi |
|---|---|
| `tests/sc05_dedupe.py` | worksheet tiruan, skenario, penilaian, laporan |
| `tests/test_sc05_dedupe.py` | 18 test, termasuk pembuktian harness bisa merah |
| `tests/_sc05_run.py` | pengukur mandiri |
| `tests/test_sc05_runner.py` | 9 test perilaku `--sc05` di runner |
| `sc-out/sc05_report.txt` | laporan teks |
| `sc-out/sc05_metrics.json` | ringkasan dalam bentuk JSON |
