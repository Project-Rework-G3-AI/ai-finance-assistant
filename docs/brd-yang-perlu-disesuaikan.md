# Yang perlu disesuaikan di BRD

Dokumen ini mencatat bagian BRD yang **tidak cocok** dengan kondisi kode dan data
yang sebenarnya. Isinya bukan usulan mengubah target, melainkan daftar hal yang
perlu diperbarui agar BRD dan kenyataan tidak saling bertentangan.

Disusun setelah mengukur ulang SC-01 sampai SC-06 pada `main` terbaru
(commit `1d251eb`). BRD hanya dibaca, tidak diubah.

## Ringkasan

| # | Bagian BRD | Isi BRD | Kenyataan | Sifat |
|---|---|---|---|---|
| 1 | SC-01 | 132 baris berlabel | `pairs.csv` berisi 65 | angka perlu diperbaiki |
| 2 | SC-02 | 118 gambar dijalankan | 65 dipakai, 118 tersedia | angka perlu diperbaiki |
| 3 | SC-02 | field wajib: tanggal, nominal, **pihak** | tidak ada field `pihak` | definisi perlu disesuaikan |
| 4 | SC-04 | biaya $0,000254–$0,000777 | terukur $0,001213 | perkiraan terlalu rendah |
| 5 | SC-05 | duplikat dikenali lewat **hash berkas** | tidak ada hash di kode | syarat teknis tidak ada |
| 6 | SC-06 | "seluruh kolom wajib" | 1 kolom diisi manusia | perlu penegasan lingkup |
| 7 | SC-07 | 147 transaksi Januari 2026 | 134 baris di 3 template | angka perlu diperbaiki |

## 1. Jumlah baris berlabel SC-01

**BRD:** *"Membandingkan usulan sistem dengan **132 baris berlabel** Januari 2026
yang sudah diisi manual."*

**Kenyataan:** `pairs.csv` di repo dataset berisi **65 baris**, dan itulah yang
dipakai mengukur SC-01. Angka 132 tidak muncul di mana pun dalam data.

**Perlu disesuaikan:** ganti 132 menjadi 65, atau jelaskan kalau 132 adalah
rencana awal yang tidak terealisasi.

## 2. Jumlah gambar uji SC-02

**BRD:** *"Menjalankan seluruh **118 gambar** Januari 2026."*

**Kenyataan:** repo dataset memang berisi **118 foto**, tetapi hanya **65** yang
punya nilai acuan di `pairs.csv`. 53 foto sisanya tidak berlabel, sehingga tidak
bisa dinilai "terbaca benar" karena tidak ada pembandingnya.

**Perlu disesuaikan:** sebutkan bahwa 118 tersedia tetapi yang dinilai 65, atau
lengkapi label untuk 53 foto sisanya bila memang ingin mengukur seluruhnya.

Catatan: memakai 65 adalah keputusan tim, bukan kekurangan. Yang perlu
diperbaiki hanya angkanya di BRD agar tidak menimbulkan pertanyaan saat dibaca
berdampingan dengan laporan.

## 3. Field wajib SC-02 menyebut "pihak"

**BRD:** *"Kelengkapan pembacaan field wajib (**tanggal, nominal, dan pihak**)."*

**Kenyataan:** kode tidak punya field `pihak` sama sekali.

```
grep -niE "pihak" main.py cash_report/*.py tests/*.py   -> kosong
```

Yang ada dan diukur: `tanggal`, `nominal`, `bank` (kantong), `arah`, `kategori`.
`pairs.csv` juga tidak punya kolom `pihak`; nama pihak hanya muncul sebagai
bagian teks `keterangan` pada 2 dari 65 baris.

**Perlu disesuaikan:** ganti "pihak" menjadi field yang benar-benar ada, atau
nyatakan bahwa pihak terbaca sebagai bagian dari `keterangan`. Kalau BRD tetap
menuntut `pihak` sebagai field tersendiri, itu berarti ada pekerjaan produksi
(menambah field), bukan pekerjaan testing.

## 4. Perkiraan biaya SC-04

**BRD:** biaya $0,000254 sampai $0,000777 per gambar.

**Kenyataan:** hasil ukur 65 gambar memberi rata-rata **$0,001213 ≈ Rp22,10**,
yaitu **1,6× di atas batas atas** perkiraan BRD. Rinciannya: prompt 937 token ×
$0,00000015 + completion 1.787 token × $0,0000006, kurs 18.227 IDR/USD.

Target <Rp50 tetap tercapai, tetapi dasar perhitungannya keliru. Model yang
dipakai (`deepseek/deepseek-v4.1-flash-1017`) membalas jauh lebih banyak token
daripada yang diasumsikan.

**Perlu disesuaikan:** perbarui rentang perkiraan agar mencerminkan token
sebenarnya, atau sebutkan model dan tarif yang dipakai saat menghitung.

## 5. Duplikat dikenali lewat hash berkas

**BRD:** *"Pemeriksaan duplikat berbasis **hash berkas** sebelum pemrosesan"*, dan
UC-03 menyebut *"Sistem mengenali berkas identik melalui **hash**"*.

**Kenyataan:** kode tidak memakai hash sama sekali.

```
grep -niE "hashlib|sha256|md5" main.py   -> kosong
```

Deduplikasi memakai `ref_id`: `tg:{file_id}` untuk Telegram dan
`manual:{nama_file}` untuk API. Akibatnya:

| Skenario | Duplikat ditolak |
|---|---|
| Kirim ulang berkas yang sama | **5 dari 5** |
| Isi sama, `file_id` berbeda | **0 dari 5** |

SC-05 tetap TERCAPAI karena target BRD berbunyi "seluruh duplikat ditolak" pada
berkas yang dikirim ulang. Tetapi kalimat "berbasis hash" di BRD tidak
menggambarkan kode yang ada.

**Perlu disesuaikan:** hapus penyebutan hash, atau nyatakan hash sebagai rencana
pengembangan. Kalau hash tetap diwajibkan, itu pekerjaan produksi di `main.py`.

## 6. Lingkup "seluruh kolom wajib" SC-06

**BRD:** *"Tidak ada kolom wajib yang hilang."*

**Kenyataan:** template perusahaan punya 10 kolom. Sembilan dihasilkan atau
diwakili aplikasi; satu kolom, `TANGGAL INPUT DAN NAMA ADMIN`, diisi manusia
karena bot menerima gambar bukti transaksi, bukan identitas pengunggahnya.

**Perlu disesuaikan:** tegaskan apakah "kolom wajib" berarti seluruh 10 kolom
template, atau hanya kolom yang datanya berasal dari bukti transaksi. Penafsiran
pertama membuat SC-06 tidak mungkin tercapai tanpa menambah pencatatan identitas
admin di produksi.

## 7. Jumlah transaksi SC-07

**BRD:** *"Admin Keuangan menyelesaikan **147 transaksi** Januari 2026."*

**Kenyataan:** tiga template Januari 2026 berisi **134 baris** berisi keterangan:

| Berkas | Baris |
|---|---|
| Cash Report BNI (sheet Januari) | 85 |
| Cash Report BRI (sheet Januari) | 15 |
| Cash Report Operasional (sheet Januari) | 34 |
| **Total** | **134** |

Selisih 13 baris. Kemungkinan ada transaksi di luar tiga rekening itu, atau
hitungannya memakai dasar berbeda (misalnya termasuk baris saldo awal).

**Perlu disesuaikan:** samakan angkanya, atau sebutkan dasar perhitungannya.

## Yang TIDAK perlu diubah

Bagian BRD yang sudah cocok dengan kenyataan, jadi jangan diutak-atik:

| Bagian | Isi BRD | Status |
|---|---|---|
| SC-01 target | minimal 85% | cocok |
| SC-03 target | rata-rata di bawah 5 detik | cocok |
| SC-04 target | di bawah Rp50 per gambar | cocok |
| SC-05 target | seluruh duplikat ditolak | cocok |
| SC-06 target | tidak ada kolom wajib yang hilang | cocok, lingkupnya perlu dipertegas |
| Tabel Success Criteria | ada di tabel #6 dokumen, 7 baris | cocok |

## Catatan cara membaca

Angka-angka di atas diambil dari sumber aslinya, bukan dari catatan turunan:

- jumlah gambar dan `pairs.csv` — repo dataset, dihitung ulang
- kolom wajib dan jumlah baris template — berkas `.xlsx` perusahaan, dibaca
  langsung dengan `openpyxl`
- biaya — CSV token hasil ukur SC-04, dikalikan tarif dan kurs
- hash dan field `pihak` — pencarian di `main.py` dan `cash_report/`

Tidak ada angka di dokumen ini yang berasal dari ringkasan sebelumnya tanpa
diperiksa ulang ke sumbernya.
