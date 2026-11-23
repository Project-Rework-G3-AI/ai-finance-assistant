# SC-01 — Hasil evaluasi akurasi kategori

Dokumen ini mencatat hasil pengukuran kriteria keberhasilan **SC-01** pada BRD:
akurasi usulan kategori dibandingkan kategori yang ditetapkan Admin, dengan
target minimal 85%.

Angka di bawah berasal dari satu eksekusi nyata, bukan perkiraan. Perintah dan
berkas pendukungnya disertakan agar hasil bisa diperiksa ulang.

## Ringkasan

| Metrik | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Run 6 |
|---|---|---|---|---|---|---|
| Total pasangan diuji | 65 | 65 | 65 | 65 | 65 | 65 |
| Benar | 10 | 9 | 8 | 3 | 5 | 7 |
| **Akurasi** | **15,4%** | **13,8%** | **12,3%** | **4,6%** | **7,7%** | **10,8%** |
| Baseline kelas mayoritas | 75,4% | 75,4% | 75,4% | 75,4% | 75,4% | 75,4% |
| **Lift atas baseline** | **−60,0%** | **−61,5%** | **−63,1%** | **−70,8%** | **−67,7%** | **−64,6%** |
| Macro-average recall | 52,9% | 52,4% | 42,4% | 40,4% | 41,2% | 22,4% |
| Target BRD | 85% | 85% | 85% | 85% | 85% | 85% |
| Status | **Belum tercapai** | **Belum tercapai** | **Belum tercapai** | **Belum tercapai** | **Belum tercapai** | **Belum tercapai** |

Enam eksekusi pada data yang sama memberi akurasi antara **4,6% dan 15,4%**,
rentang **10,8 poin persen**, dengan rata-rata 10,8%. Kode sudah mengirim
`temperature: 0`, tetapi model penalaran lewat API pihak ketiga tidak menjamin
determinisme penuh, dan tidak ada parameter `seed`.

Model memang menjawab berbeda-beda, bukan gagal. Pada satu run ia memilih 17
kategori berbeda untuk 65 gambar. Namun pada run 5 dan run 6 ada 1 dan 2 baris
yang jatuh ke `mock` karena model membalas `content: null`, dan parser di
`main.py` baris 135 belum menangani nilai kosong itu. Baris tersebut tercatat
salah karena kategorinya kosong, sehingga ikut menekan akurasi.

Karena itu satu angka saja menyesatkan. Yang stabil di keempat run: akurasi
berada jauh di bawah baseline 75,4% dan jauh dari target 85%. Bahkan pada run
terbaik, model kalah 60 poin persen dari tebakan konstan.

Akurasi belasan persen berada di bawah baseline. Artinya model bukan hanya belum
mencapai target, tetapi lebih buruk daripada menjawab `Transfer Antar Bank` untuk
setiap gambar tanpa melihat isinya.

## Cara pengukuran

Langkah menjalankan evaluasi ini di komputer lokal ada di
[`sc01-cara-menjalankan.md`](sc01-cara-menjalankan.md). Ringkasnya:

```bash
python3 tests/sc01_harness.py --download   # unduh 65 gambar (sekali)
python3 tests/sc01_harness.py             # jalankan evaluasi
```

| Komponen | Perlakuan |
|---|---|
| Model | Asli — `deepseek/deepseek-v4.1-flash-1017` lewat OpenRouter |
| `main.extract` | Dipanggil apa adanya, tidak diubah |
| Google Sheets | Tidak dipanggil sama sekali |
| Google Drive | Tidak dipanggil sama sekali |
| Dataset | 65 pasangan gambar–baris, pemetaan 1:1 |

Penulisan ke Sheets dan Drive sengaja tidak dijalankan agar spreadsheet
perusahaan tidak tersentuh dan hasil bisa diulang. Batas ini dijaga oleh
`test_runner_tidak_menulis_ke_sheets_atau_drive`.

## Lokasi data

Daftar pasangan dan gambarnya tidak disimpan di repo ini karena repo bersifat
publik dan datanya berisi transaksi perusahaan.

| Berkas | Lokasi |
|---|---|
| Daftar 65 pasangan | `sc01/sc01_pairs.csv` di repo privat `Project-Rework-G3-AI/rework-ai-finance-assistant-dataset` |
| 118 gambar bukti | `Bukti Transaksi Januari 2026/` di repo yang sama |
| Harness dan test | `tests/sc01_*.py` di repo ini |

Repo dataset dipisah dan privat supaya seluruh anggota kelompok bisa mengakses
data yang sama, tidak bergantung pada satu orang. `--download` mengambil daftar
pasangan lalu gambarnya memakai `GITHUB_TOKEN` pribadi masing-masing. Setelah ada
di disk, evaluasi berjalan lokal sepenuhnya.

## Mengapa 65, bukan 132

BRD menyebut 132 baris berlabel Januari. Jumlah itu tidak bisa dipakai sebagai
penyebut karena tidak sebanding dengan jumlah gambar:

| | Jumlah |
|---|---|
| Baris berlabel Januari | 132 |
| Gambar bukti transaksi | 118 |
| Baris yang bisa dipasangkan 1:1 dengan gambar | **65** |

Sebanyak 67 baris tidak punya gambar sama sekali — QRIS, virtual account, bunga
bank, biaya admin, parkir, dan setoran MPN tidak menghasilkan bukti transfer.
Mengukur akurasi pada 132 baris berarti memasukkan baris yang gambarnya tidak
pernah ada, sehingga angkanya turun bukan karena model salah membaca, melainkan
karena tidak ada yang bisa dibaca.

## Sebaran kategori pada set uji

| Kategori acuan | Jumlah | Benar | Recall |
|---|---|---|---|
| `Transfer Antar Bank` | 49 | 7 | 14% |
| `Pendapatan Usaha (Penjualan Lainnya)` | 12 | 0 | 0% |
| `Biaya-Perlengkapan Kantor dan Administrasi` | 2 | 1 | 50% |
| `Biaya-Gaji Karyawan` | 1 | 1 | 100% |
| `Biaya-Transportasi` | 1 | 1 | 100% |

Recall 100% pada dua kategori terakhir tidak boleh dibaca sebagai keberhasilan:
masing-masing hanya berisi satu baris.

## Uraian kesalahan

Dari 55 baris yang salah:

| Jumlah | Pola |
|---|---|
| 41 | Acuan `Transfer Antar Bank`, model memberi kategori rinci (`Bahan Baku`, `Biaya-Ongkir`, dan sejenisnya) |
| 8 | Acuan kategori rinci, model memberi `Transfer Antar Bank` |
| 4 | Lain-lain |
| 1 | Acuan `Pendapatan Usaha (Penjualan Lainnya)`, model memberi pecahan pendapatan lain |
| 1 | Acuan `Transfer Antar Bank`, model tidak menjawab karena galat |

Pola terbesar bukan model salah membaca. Contohnya, bukti transfer Rp640.350
tertulis jelas "Mocaf 50 kg" dan model menjawab `Bahan Baku` — secara isi benar,
karena itu memang pembelian bahan baku. Admin mencatatnya sebagai
`Transfer Antar Bank` karena kolom tersebut mencatat jalur pembayaran.

Kedua jawaban sah dan sama-sama ada di dropdown yang sama. Yang berbeda adalah
tingkat kerinciannya. Karena itu SC-01 tidak bisa mencapai 85% selama kategori
acuan memakai granularitas kasar: model yang menjawab dengan benar secara isi
tetap dihitung salah.

## Satu galat yang ditemukan

Satu dari 65 gambar gagal karena `main.py` baris 135–136:

```python
text = r.json()["choices"][0]["message"]["content"]
m = re.search(r"\{.*\}", text, re.S)
```

Ketika model mengembalikan `content` bernilai `null`, `re.search` menerima
`None` dan melempar `TypeError: expected string or bytes-like object, got
'NoneType'`. `extract()` menangkapnya lalu jatuh ke mock, sehingga kategori
menjadi kosong dan baris tetap tercatat seolah berhasil.

Akibatnya bukan hanya satu baris hilang: pengguna melihat balasan "Draft
tercatat" padahal kategorinya tidak pernah terisi.

## Berkas pendukung

| Berkas | Isi |
|---|---|
| `tests/sc01_metrics.py` | Perhitungan akurasi, baseline, lift, macro-average, confusion matrix |
| `tests/sc01_harness.py` | Runner: panggil model, simpan hasil per baris, tulis laporan |
| `tests/test_sc01_accuracy.py` | Test rumus metrik dan batas ruang lingkup |
| `hasil_per_baris.csv` | Keluaran per gambar (tidak di-commit; berisi data transaksi) |

Hasil ditulis bertahap ke CSV setelah setiap gambar selesai diproses. Pada run
pertama di sesi sebelumnya proses sempat mati setelah puluhan panggilan API
berbayar; penulisan bertahap inilah yang menyelamatkan hasilnya.

## Kesimpulan

SC-01 belum tercapai dan tidak dapat dicapai tanpa lebih dulu menyelesaikan
masalah granularitas kategori. Kesimpulan ini berlaku pada kedua run, terlepas
dari selisih dua poin persen di antaranya.

Dua langkah yang masuk akal, dan keduanya perlu keputusan pemilik produk:

1. **Menyamakan granularitas.** Tetapkan satu tingkat kerincian untuk kolom
   kategori, lalu ukur ulang. Bila acuan memakai tingkat rinci, model yang
   sekarang sudah menjawab rinci berpeluang besar lolos 85%.
2. **Mengukur pada baris yang punya padanan rinci.** Batasi SC-01 pada baris
   yang acuannya bukan `Transfer Antar Bank`, lalu laporkan sisanya terpisah
   sebagai kasus yang tidak dapat dinilai.

Yang tidak boleh dilakukan adalah melaporkan angka belasan persen tanpa menyebut
baseline 75,4%, karena pembaca akan menyimpulkan modelnya hampir benar padahal
kalah dari tebakan konstan.
