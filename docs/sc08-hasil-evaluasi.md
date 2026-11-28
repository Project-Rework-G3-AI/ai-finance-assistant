# SC-08: Tanya jawab analitik keuangan

Dokumen ini mencatat cara SC-08 diukur, angka pembandingnya, dan batas
pengukurannya.

## Apa yang diukur

BRD menetapkan SC-08 sebagai **tanya jawab analitik keuangan** dengan target
seluruh jawaban sesuai. Yang diukur di sini adalah satu hal: apakah angka yang
disebut dalam jawaban sama dengan angka di spreadsheet.

Susunan kalimat, urutan penyajian, dan panjang penjelasan **tidak** dinilai.
Jawaban pendek yang menyebut angka benar dinyatakan lulus. Jawaban panjang yang
terdengar meyakinkan tetapi menyebut angka salah dinyatakan gagal.

## Cara mengukur

Empat pertanyaan baku diajukan ke jalur jawaban produksi
(`cash_report.qa.answer_question`), yaitu fungsi yang sama yang dipakai bot saat
Admin Keuangan bertanya lewat Telegram. Pertanyaannya tetap, tidak berubah antar
run, karena membandingkan jawaban terhadap daftar pertanyaan yang bergerak tidak
mengukur apa pun.

| ID | Pertanyaan | Angka yang harus muncul |
|---|---|---|
| Q1 | Total uang masuk dan keluar Januari 2026, verified dan draft terpisah | masuk verified, masuk draft, keluar verified, keluar draft |
| Q2 | Nominal Transfer Antar Bank, dan apakah dihitung pemasukan/pengeluaran | nominal transfer |
| Q3 | Tiga kategori pengeluaran terbesar beserta nominalnya | tiga nominal teratas |
| Q4 | Jumlah baris Januari 2026 dan berapa yang masih draft | jumlah baris, jumlah draft |

## Kenapa pembandingnya mandiri

Ini bagian terpenting dari pengukuran ini.

Kalau angka pembanding diambil dengan memanggil `cash_report.qa.aggregate`, maka
yang terjadi adalah bot dibandingkan dengan dirinya sendiri. Kedua sisi memakai
fungsi yang sama. Kalau fungsi itu salah hitung, salahnya muncul di kedua sisi
dan hasilnya tetap "cocok". Pengukuran seperti itu hanya membuktikan fungsinya
deterministik, bukan bahwa jawabannya benar.

Karena itu pembanding dihitung `tests/_sc08_reference.py`, yang membaca baris
mentah ledger (A2:K) dengan parser tanggal dan parser angka sendiri, lalu
menerapkan aturan yang dinyatakan ulang di berkas itu:

| Aturan | Arti |
|---|---|
| periode setengah terbuka | 31 Januari masuk, 1 Februari tidak |
| Transfer Antar Bank bukan pemasukan dan bukan pengeluaran | hanya sisi masuknya dihitung, di kantong terpisah |
| verified dan draft tidak dicampur | baris draft bukan angka resmi |
| tanggal tak terbaca di luar semua periode | termasuk di luar total |

Berkas itu **tidak mengimpor** `cash_report` maupun `main`, dan ada test yang
menegakkannya dengan membaca pohon impor lewat `ast`. Test itu sengaja tidak
mencari teks, karena kata "cash_report" muncul di penjelasan sebagai alasan, dan
pencarian teks akan salah menuduhnya.

## Sumber data

Ledger untuk pengukuran ini disusun dari hasil ekstraksi yang **sudah ada**
(`sc-out/results_per_row.csv`), bukan dari memanggil model ulang. Alasannya:
kriteria ini soal jawaban atas data yang tercatat, bukan soal membaca bukti
transaksi lagi. Kalau model dipanggil ulang setiap kali SC-08 diukur, angkanya
akan berubah dan hasilnya tidak bisa dibandingkan antar run.

Penyusunnya `tests/_sc08_ledger.py`. Bentuk barisnya meniru apa yang ditulis
`write_cash_report()`, karena jalur jawaban membaca kolom persis itu.

| Kolom | Isi |
|---|---|
| A | tanggal `YYYY-MM-DD HH:MM:SS` |
| B | kantong |
| C | masuk |
| D | keluar |
| E | kategori |
| F | keterangan |
| G | status, `verified` atau `draft` |
| H | catatan |
| I | Ref ID |
| J | nama berkas sumber |
| K | tautan bukti |

Ada satu tambahan yang disengaja: transaksi berkategori `Transfer Antar Bank`
ditulis sebagai dua baris berpasangan, dan sisi masuknya ditandai `verified`.
Tanpa itu ledger hanya berisi baris keluar, aturan "transfer bukan pemasukan"
tidak akan pernah terlihat, dan pengukurannya diam-diam tidak membuktikan apa pun
soal aturan itu.

Hasil penyusunan dari 65 baris ekstraksi:

| Hal | Jumlah |
|---|---|
| baris hasil ekstraksi | 65 |
| dilewati: nominal tidak terbaca | 1 |
| bertambah: sisi masuk transfer | 8 |
| **baris ledger** | **72** |
| di dalam periode Januari 2026 | 71 |
| di luar periode | 1 |

Baris yang dilewati adalah `photo_2026-01-05_09-57-49.jpg`, yang nominalnya
kosong pada hasil ekstraksi. Baris di luar periode berasal dari
`photo_2026-01-08_09-21-46.jpg`: berkasnya bertanggal 8 Januari, tetapi model
membaca tanggal transaksi **28 September 2025**. Pembanding dan bot sama-sama
mengeluarkannya dari Januari 2026, jadi keduanya konsisten; tetapi ini temuan
tersendiri soal pembacaan tanggal, dicatat di bagian batas di bawah.

## Angka pembanding

Dihitung `tests/_sc08_reference.py` dari 71 baris dalam periode:

| Angka | Nilai |
|---|---|
| masuk verified | 1.932.685,00 |
| keluar verified | 15.671.353,00 |
| masuk draft | 0,00 |
| keluar draft | 35.000,00 |
| baris draft | 1 |
| baris dalam periode | 71 |
| transfer masuk | 1.607.294,00 |
| baris transfer | 17 |

Tiga kategori pengeluaran terbesar, diurutkan menurut uang **keluar**:

| Peringkat | Kategori | Nominal |
|---|---|---|
| 1 | Bagi Hasil | 2.705.329,00 |
| 2 | Bahan Baku | 2.381.697,00 |
| 3 | Beban Operasional-Pelatihan | 2.252.325,00 |

## Hasil

**Belum tercapai: 2 dari 4 run menjawab seluruh pertanyaan dengan angka yang
benar.** Targetnya seluruh jawaban sesuai, dan target itu belum terpenuhi karena
pertanyaan Q4 kadang dijawab dengan angka yang salah.

Diukur empat kali berturut-turut dengan pertanyaan dan data yang sama:

| Run | Q1 | Q2 | Q3 | Q4 | Jumlah cocok |
|---|---|---|---|---|---|
| 1 | cocok | cocok | cocok | cocok (71 baris) | **4 dari 4** |
| 2 | cocok | cocok | cocok | **salah (70 baris)** | 3 dari 4 |
| 3 | cocok | cocok | cocok | cocok (71 baris) | **4 dari 4** |
| 4 | cocok | cocok | cocok | **salah (15 baris)** | 3 dari 4 |

Q1, Q2, dan Q3 konsisten benar di keempat run. Yang tidak konsisten hanya Q4,
yaitu pertanyaan tentang **jumlah baris**.

| Run | Angka yang disebut Q4 | Angka sebenarnya | Selisih |
|---|---|---|---|
| 1 | 71 baris | 71 | 0 |
| 2 | 70 baris | 71 | 1 baris kurang |
| 3 | 71 baris | 71 | 0 |
| 4 | 15 baris | 71 | 56 baris kurang |

Jawaban Q2 juga menyebut hal yang tidak diminta secara eksplisit tetapi penting:
transfer **tidak** dihitung sebagai pemasukan maupun pengeluaran. Itu sesuai
aturan yang tertulis di prompt produksi.

Q1 menjawab angka nol untuk masuk draft dengan kalimat "Draft: tidak ada", bukan
dengan menuliskan "0". Penilainya menerima itu, karena pernyataan "tidak ada"
adalah cara yang benar menyatakan nol. Yang tidak diterima adalah jawaban tanpa
angka sama sekali, misalnya "maaf saya tidak bisa membantu".

## Kenapa Q4 kadang salah

Ini bukan kesalahan penilai, dan bukan model berhalusinasi. Ada dua sebab di kode
produksi, keduanya bisa dibuktikan tanpa memanggil model.

**Sebab pertama: daftar baris dipotong, dan pemotongannya tidak diberitahukan.**

`cash_report/qa.py` membatasi `list_rows` pada 50 baris:

```python
if len(out) >= max(1, min(int(limit or 15), 50)):
    break
```

Batas atas 50 itu berlaku mutlak. Meminta 100 pun tetap menghasilkan 50. Diuji
langsung: `qa.list_rows(rows, awal, akhir, limit=100)` mengembalikan **50** baris
untuk 71 baris data, tanpa satu pun tanda bahwa hasilnya terpotong.

Model lalu menghitung sendiri dari daftar yang sudah terpotong. Pada run keempat
model hanya mengambil 15 baris (batas bawaan) dan melaporkan "15 baris" sebagai
jumlah seluruh transaksi. Angka itu bukan karangan: itu memang jumlah baris yang
diberikan kepadanya. Yang salah adalah alat tidak pernah memberi tahu bahwa yang
diberikan hanya sebagian.

**Sebab kedua: jumlah baris per status tidak pernah dilaporkan.**

`aggregate` mengembalikan `n` per status, tetapi itu dihitung dari `_pilih` yang
menyaring `arah`, sehingga angkanya bukan jumlah baris. Yang tersedia:

| Sumber | Angka | Arti sebenarnya |
|---|---|---|
| `aggregate()["verified"]["n"]` | 53 | baris verified yang bukan transfer |
| `aggregate()["draft"]["n"]` | 1 | baris draft yang bukan transfer |
| `aggregate()["transfer"]["n_verified"]` | 17 | baris transfer, termasuk sisi keluar |
| jumlah baris dalam periode | **71** | tidak pernah dilaporkan ke model |

Tidak ada satu pun hasil tool yang menyebut 71. Pada run ketiga model tetap
menjawab 71 dengan benar, dan itu bukan karena alat memberitahunya, melainkan
karena ia memilih menjumlahkan sendiri angka-angka lain. Pada run kedua model
menjumlahkan dengan cara yang berbeda dan mendapat 70. Jadi jawaban benar pada
run ketiga berasal dari cara model menebak, bukan dari data yang disediakan.
Karena itu hasilnya tidak dapat diandalkan.

**Ini melanggar aturan yang tertulis di prompt produksi sendiri**, yang berbunyi
angka hanya boleh berasal dari hasil tool, tidak dihitung atau diingat sendiri.
Untuk pertanyaan jumlah baris, aturan itu tidak mungkin dipatuhi karena tidak ada
tool yang menyediakannya.

## Batas pengukuran

**Pertanyaannya sedikit dan buatan.** Empat pertanyaan tidak mewakili seluruh
pertanyaan yang mungkin diajukan Admin Keuangan. Yang diukur adalah apakah jalur
jawaban mengambil angka dari data dan melaporkannya apa adanya, bukan kemampuan
menjawab segala bentuk pertanyaan.

**Datanya satu bulan dan satu ledger.** Januari 2026 saja. Perilaku pada bulan
dengan data kosong, data sangat besar, atau data yang belum punya baris verified
sama sekali belum diukur.

**Jawaban yang benar tidak membuktikan alasannya benar.** Penilai memeriksa angka
yang muncul, bukan bagaimana angka itu diperoleh. Jawaban yang menyebut angka
benar karena kebetulan cocok akan tetap lulus.

**Q3 dan Q4 memakai lebih dari satu putaran tool.** Log mencatat "putaran tool
habis, paksa rangkuman" pada keduanya di sebagian besar run. Artinya model meminta
tool lebih banyak daripada yang diizinkan, lalu jawaban terakhir dipaksa tanpa
tool. Q3 tetap benar karena nominalnya diambil dari hasil tool sebelumnya. Q4
tidak, karena jumlah baris tidak pernah tersedia di hasil tool mana pun.

**Jumlah baris tidak dapat dijawab dengan andal.** Ini batas terbesar pengukuran
ini, dan sekaligus temuannya. Tiga pertanyaan lain (Q1, Q2, Q3) mengukur angka
yang memang disediakan tool, jadi hasilnya stabil. Q4 mengukur angka yang tidak
disediakan tool, sehingga jawabannya bergantung pada cara model menjumlahkan
sendiri. Selama alat tidak menyediakan jumlah baris dan tidak memberi tahu bahwa
daftarnya terpotong, hasil Q4 akan terus berubah antar run.

**Satu baris bertanggal salah.** `photo_2026-01-08_09-21-46.jpg` bertanggal
berkas 8 Januari, tetapi model membacanya sebagai 28 September 2025. Baris itu
keluar dari periode Januari. Pembanding dan bot sama-sama mengeluarkannya
sehingga hasil SC-08 tidak terpengaruh, tetapi pembacaan tanggalnya salah dan
belum ditangani.

## Cara menjalankan ulang

```bash
python3 tests/_sc08_run.py --ledger sc-out/sc08_ledger.csv
python3 tests/sc_runner.py --sc08
```

Perintah pertama memanggil model dan berbayar. Perintah kedua hanya merangkum
sampel yang sudah ada dan gratis. Bila `sc08_samples.json` belum ada, perintah
kedua berhenti dengan pesan yang menyebutkan perintah pertama, bukan menjalankan
model diam-diam.

Karena hasilnya belum stabil, satu kali run **tidak cukup** untuk menyimpulkan
apa pun tentang Q4. Ukur beberapa kali, lalu laporkan sebarannya seperti tabel
hasil di atas.
