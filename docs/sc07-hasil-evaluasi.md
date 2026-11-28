# SC-07: Rekonsiliasi mutasi rekening bank

## Apa yang diukur

Apakah **saldo akhir** hasil hitung sistem sama dengan saldo akhir yang
tercetak pada mutasi rekening bank.

Satu hal saja. Jumlah transaksi, total debet, dan total kredit ditampilkan
sebagai angka pendukung, tetapi **tidak dipakai menilai** kriteria ini. Kalau
ikut dinilai, kriterianya diam-diam berubah menjadi kriteria lain dengan
penyebut berbeda.

Target dari BRD: saldo akhir sama pada kedua rekening.

## Hasil

**Tercapai: 2 dari 2 rekening**, dan sekarang pada setiap percobaan.

| Rekening | Saldo akhir tercetak | Saldo akhir sistem | Selisih |
|---|---|---|---|
| BNI 1783680837 | 9.556.974,00 | 9.556.974,00 | 0,00 |
| BRI 306601000009566 | 192.643.952,00 | 192.643.952,00 | 0,00 |

Angka ini sama dengan pengukuran sebelumnya. Yang berubah bukan hasilnya,
melainkan **kesempatan hasil itu tercapai**: dulu dua dari empat percobaan
berhenti di tengah, sekarang empat dari empat percobaan selesai penuh.

Penyebabnya satu: balasan model yang kadang datang kosong, dan jalur rekonsiliasi
tidak pernah mencoba ulang. Setelah percobaan ulang ditambahkan, kejadian yang
sama tertangani sendiri.

Angka pendukung, semuanya juga cocok:

| Rekening | Saldo awal | Total debet | Total kredit |
|---|---|---|---|
| BNI | 2.180.712,00 | 13.049.913,00 | 20.426.175,00 |
| BRI | 214.531.779,00 | 22.066.136,00 | 178.309,00 |

Ketepatan pembacaan transaksi:

| Rekening | Transaksi tercetak | Transaksi terbaca sistem | Validasi saldo berjalan |
|---|---|---|---|
| BNI | tidak dihitung | 84 | lolos |
| BRI | 14 | 14 | lolos |

Model: `deepseek/deepseek-v4.1-flash-1017`. Pengukuran yang berhasil memerlukan
93,43 detik untuk BNI (7 halaman) dan 15,76 detik untuk BRI (2 halaman).

## Kestabilan: sebelum dan sesudah perbaikan

**Sebelum perbaikan, 2 dari 4 percobaan selesai penuh.**

| Percobaan | BNI | BRI | Penyebab berhenti |
|---|---|---|---|
| 1 | cocok | cocok | selesai penuh |
| 2 | gagal | gagal | `Empty AI response on page 3` (BNI), `page 1` (BRI) |
| 3 | cocok | cocok | selesai penuh |
| 4 (clone bersih) | cocok | gagal | `Empty AI response on page 1` (BRI) |

BNI gagal 1 kali, BRI gagal 2 kali, dan **tidak ada rekening yang gagal di
halaman yang sama dua kali**. Artinya kegagalan ini tidak menempel pada halaman
atau berkas tertentu, melainkan pada balasan model yang kadang datang kosong.

**Sesudah perbaikan, 4 dari 4 percobaan selesai penuh.**

| Percobaan | Balasan kosong yang diulang | BNI | BRI |
|---|---|---|---|
| 1 | tidak ada | cocok | cocok |
| 2 | tidak ada | cocok | cocok |
| 3 | **2 kali** (BNI halaman 2, BRI halaman 1) | cocok | cocok |
| 4 (clone bersih) | tidak ada | cocok | cocok |

Percobaan ketiga adalah buktinya. Dua halaman membalas kosong, keduanya diulang,
dan kedua rekening tetap berakhir dengan saldo yang cocok. Sebelum perbaikan,
percobaan seperti ini akan berhenti dan tidak menghasilkan apa pun.

Yang perlu dicatat: `reconciliation/vision_extractor.py` **tidak punya percobaan
ulang untuk balasan kosong**. `post_with_retry` hanya mengulang pada galat HTTP
500, 502, 503, dan 504. Balasan kosong langsung menjadi `ValueError` dan seluruh
proses rekonsiliasi berhenti — berbeda dari `main.py`, yang sudah menangani
balasan kosong.

Akibatnya, bila ini terjadi di produksi, satu halaman yang gagal membuat seluruh
mutasi tidak dapat direkonsiliasi, bukan hanya satu baris.

**Sudah diperbaiki.** `reconciliation/vision_extractor.py` sekarang mengulang
permintaan bila balasannya kosong atau bukan JSON, sampai tiga kali percobaan
dengan jeda singkat. Galat HTTP tetap ditangani `post_with_retry`, jadi tidak ada
permintaan yang diulang oleh dua lapisan sekaligus. Perilakunya dijaga
`tests/test_reconciliation_retry.py`.

## Kenapa hasil ini bisa dipercaya

Yang menentukan bukan angkanya, melainkan **asal pembandingnya**.

| Rekening | Asal pembanding | Mandiri dari model? |
|---|---|---|
| BRI | lapisan teks PDF | ya |
| BNI | dibaca manual dari halaman 1 | ya |

**BRI** punya lapisan teks. Saldo awal, total debet, total kredit, dan saldo
akhir dibaca langsung dari teks PDF memakai pencocokan pola, tanpa memanggil
model. Pembanding ini juga diperiksa mandiri:

- saldo awal + kredit - debet = 192.643.952,00, sama dengan saldo akhir tercetak;
- saldo berjalan tiap baris berkesinambungan, tidak ada satu pun yang meleset;
- 14 transaksi terbaca, sesuai jumlah baris di PDF.

**BNI** adalah hasil pindai: 7 halaman, **0 karakter teks**. Angkanya tidak
dapat dibaca tanpa model atau mata manusia. Karena itu dibaca manual dan
dicatat di `tests/_sc07_bni_reference.json`:

| Hal | Isi |
|---|---|
| Nomor rekening | 1783680837 |
| Pemilik | ILHAM NAWAN RASYID |
| Periode | 1 sampai 31 Januari 2026 |
| Letak angka | kotak ringkasan di bagian atas halaman 1 |
| Pemeriksaan | 2.180.712 + 20.426.175 - 13.049.913 = 9.556.974 |

Pembacaan manual itu bukan jalan pintas. Kalau saldo akhir BNI dibaca oleh
model yang sama dengan yang diuji, yang terjadi adalah **model dibandingkan
dengan model**, dan hasilnya tidak mengukur apa pun. Letak angkanya sengaja
dicatat supaya orang lain bisa membuka halaman yang sama dan memeriksa sendiri.

## Kenapa kecocokan saldo akhir cukup menuntut

Saldo akhir adalah angka turunan: ia hanya benar bila **seluruh** transaksi
terbaca dengan nominal dan arah yang benar. Satu transaksi hilang, satu nominal
salah baca, atau satu arah tertukar akan membuat saldo akhir meleset.

Karena itu kecocokan saldo akhir lebih ketat daripada menghitung berapa banyak
baris yang berhasil dipasangkan. Pada BNI, 84 transaksi terbaca dan saldo
akhirnya tetap harus bertemu angka yang sama.

## Batas pengukuran ini

**Hanya dua rekening, satu bulan.** Keduanya Januari 2026. Mutasi bulan lain
belum diuji, dan format PDF bank lain belum tentu terbaca.

**Kecocokan saldo akhir tidak membuktikan tiap baris benar.** Dua kesalahan
yang saling meniadakan secara teori bisa menghasilkan saldo akhir yang sama.
Peluangnya kecil, tetapi bukan nol. Yang bisa dikatakan: tidak ada transaksi
hilang atau salah nominal yang menggeser saldo.

**Pembanding BNI tidak dapat diperiksa ulang oleh mesin.** Ia dibaca mata
manusia dan dicatat. Orang lain bisa memeriksa dengan membuka halaman 1 PDF
yang sama, tetapi tidak ada cara otomatis memverifikasinya.

**Rekonsiliasi ke Cash Report belum diukur.** SC-07 hanya membandingkan saldo
akhir mutasi dengan hasil hitung sistem. Pencocokan baris mutasi terhadap baris
Cash Report adalah pekerjaan terpisah di `reconciliation/matcher.py`, dan tidak
dinilai di sini.

## Cara menjalankan

```bash
python3 tests/_sc07_run.py            # unduh PDF mutasi bila belum ada, lalu ukur
python3 tests/sc_runner.py --sc07     # laporan, gratis
```

PDF mutasi diunduh otomatis dari repo dataset ke `dataset/mutasi/`. Nama berkas
di repo memakai spasi, sedangkan SC-07 menyimpannya dengan garis bawah;
pemetaannya ada di `STATEMENT_FILES` (`tests/sc_common.py`). Berkas yang
diunduh identik dengan aslinya, hash-nya sama, sehingga pengukuran orang lain
memakai bahan yang sama persis.

Berkas keluaran:

| Berkas | Isi |
|---|---|
| `sc07_report.txt` | laporan lengkap |
| `sc07_metrics.json` | ringkasan dalam bentuk JSON |
| `sc07_samples.json` | keluaran sistem dan pembanding per rekening |

Berkas kode:

| Berkas | Isi |
|---|---|
| `tests/_sc07_run.py` | pengukur: panggil model, bandingkan saldo akhir |
| `tests/_sc07_text_statement.py` | baca mutasi dari lapisan teks PDF, tanpa model |
| `tests/_sc07_bni_reference.json` | pembanding BNI hasil baca manual, beserta letaknya |
| `tests/sc07_reconciliation.py` | penyusun laporan dari `sc07_samples.json` |
| `tests/test_sc07_reconciliation.py` | penjaga sifat alat ukur |
