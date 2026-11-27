# SC-01 — Hasil evaluasi akurasi kategori

Dokumen ini mencatat hasil pengukuran kriteria keberhasilan **SC-01** pada BRD:
akurasi usulan kategori dibandingkan kategori yang ditetapkan Admin, dengan
target minimal 85%.

Angka di bawah berasal dari satu eksekusi nyata, bukan perkiraan. Perintah dan
berkas pendukungnya disertakan agar hasil bisa diperiksa ulang.

## Angka mana yang dibandingkan dengan target

Laporan SC-01 memuat beberapa angka sekaligus, jadi mana yang dinilai perlu
disebut terang-terangan:

| Angka | Nilai (run terbaru) | Dipakai menilai target? |
|---|---|---|
| **Akurasi** (benar / total) | **9,2%** | **ya** |
| Baseline kelas mayoritas | 75,4% | tidak, batas bawah |
| Macro-average recall | 31,6% | tidak, penjelas |
| Lift atas baseline | −66,2% | tidak, penjelas |

**Yang dibandingkan dengan target 85% adalah akurasi 9,2%**, yaitu 6 jawaban
benar dari 65 pasangan.

Alasannya: BRD menyebut "akurasi usulan kategori", dan akurasi berarti proporsi
jawaban benar terhadap seluruh pasangan. Baseline dan macro-average ditampilkan
justru untuk menunjukkan bahwa akurasi itu tidak bisa dibaca sendiri: 75,4%
baseline berarti model kalah dari sekadar menebak `Transfer Antar Bank` terus,
dan macro-average menunjukkan kategori jarang hampir tidak pernah benar.

Perhatikan bahwa **tidak ada satu pun angka di tabel ini yang mencapai 85%**,
jadi statusnya tidak bergantung pada pilihan angka. Tetapi menyebut angka mana
yang dinilai tetap penting, karena laporan yang hanya menulis "BELUM TERCAPAI"
memaksa pembaca menebak.

## Riwayat eksekusi

Akurasi diukur berulang kali karena model tidak deterministik. Semua run memakai
65 pasangan yang sama:

| Metrik | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Run 6 | Run 7 | Run 8 (terbaru) |
|---|---|---|---|---|---|---|---|---|
| Total pasangan diuji | 65 | 65 | 65 | 65 | 65 | 65 | 65 | 65 |
| Benar | 10 | 9 | 8 | 3 | 5 | 7 | 5 | **6** |
| **Akurasi** | **15,4%** | **13,8%** | **12,3%** | **4,6%** | **7,7%** | **10,8%** | **7,7%** | **9,2%** |
| Baseline kelas mayoritas | 75,4% | 75,4% | 75,4% | 75,4% | 75,4% | 75,4% | 75,4% | 75,4% |
| **Lift atas baseline** | **−60,0%** | **−61,5%** | **−63,1%** | **−70,8%** | **−67,7%** | **−64,6%** | **−67,7%** | **−66,2%** |
| Macro-average recall | 52,9% | 52,4% | 42,4% | 40,4% | 41,2% | 22,4% | 21,6% | **31,6%** |
| Target BRD | 85% | 85% | 85% | 85% | 85% | 85% | 85% | 85% |
| Status | belum | belum | belum | belum | belum | belum | belum | **belum** |

Delapan eksekusi pada data yang sama memberi akurasi antara **4,6% dan 15,4%**,
rentang **10,8 poin persen**, dengan rata-rata 10,2%. Run 8 dijalankan pada
27 November 2026, setelah prompt ekstraksi berubah (`TUNAI` menjadi `UANG KAS`,
dan aturan `arah=transfer` diperjelas). Kode sudah mengirim `temperature: 0`,
tetapi model penalaran lewat API pihak ketiga tidak menjamin determinisme penuh,
dan tidak ada parameter `seed`.

Model memang menjawab berbeda-beda, bukan gagal. Pada satu run ia memilih 17
kategori berbeda untuk 65 gambar. Namun pada beberapa run ada baris yang jatuh
ke `mock` karena model membalas `content: null`, dan parser di `main.py` belum
menangani nilai kosong itu. Baris tersebut tercatat salah karena kategorinya
kosong, sehingga ikut menekan akurasi.

Karena itu satu angka saja menyesatkan. Yang stabil di semua run: akurasi
berada jauh di bawah baseline 75,4% dan jauh dari target 85%. Bahkan pada run
terbaik, model kalah 60 poin persen dari tebakan konstan.

Akurasi belasan persen berada di bawah baseline. Artinya model bukan hanya belum
mencapai target, tetapi lebih buruk daripada menjawab `Transfer Antar Bank` untuk
setiap gambar tanpa melihat isinya.

## Cara pengukuran

Langkah menjalankan evaluasi ini di komputer lokal ada di
[`sc-cara-menjalankan.md`](sc-cara-menjalankan.md). Ringkasnya:

```bash
python3 tests/sc_runner.py --download   # unduh 65 gambar (sekali)
python3 tests/sc_runner.py             # jalankan evaluasi
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
| Daftar 65 pasangan | `pairs.csv` di repo privat `Project-Rework-G3-AI/rework-ai-finance-assistant-dataset` |
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
| `Transfer Antar Bank` | 49 | 4 | 8% |
| `Pendapatan Usaha (Penjualan Lainnya)` | 12 | 0 | 0% |
| `Biaya-Perlengkapan Kantor dan Administrasi` | 2 | 1 | 50% |
| `Biaya-Gaji Karyawan` | 1 | 0 | 0% |
| `Biaya-Transportasi` | 1 | 1 | 100% |

Recall 100% pada `Biaya-Transportasi` tidak boleh dibaca sebagai keberhasilan:
kategori itu hanya berisi satu baris.

## Uraian kesalahan

Dari 59 baris yang salah:

| Jumlah | Pola |
|---|---|
| 45 | Acuan `Transfer Antar Bank`, model memberi kategori rinci (`Bahan Baku`, `Biaya-Ongkir`, dan sejenisnya) |
| 8 | Acuan kategori rinci, model memberi kategori rinci lain |
| 5 | Acuan kategori rinci, model memberi `Transfer Antar Bank` |
| 1 | Acuan kategori rinci, model tidak menjawab karena galat |

Pola terbesar bukan model salah membaca. Contohnya, bukti transfer Rp640.350
tertulis jelas "Mocaf 50 kg" dan model menjawab `Bahan Baku` — secara isi benar,
karena itu memang pembelian bahan baku. Admin mencatatnya sebagai
`Transfer Antar Bank` karena kolom tersebut mencatat jalur pembayaran.

Kedua jawaban sah dan sama-sama ada di dropdown yang sama. Yang berbeda adalah
tingkat kerinciannya. Karena itu SC-01 tidak bisa mencapai 85% selama kategori
acuan memakai granularitas kasar: model yang menjawab dengan benar secara isi
tetap dihitung salah.

## Satu galat yang ditemukan

Pada run 8, satu dari 65 gambar (`photo_2026-01-05_09-57-49.jpg`) gagal dan jatuh
ke mode cadangan setelah menunggu 280 detik. Penyebabnya model membalas dengan
`content` kosong:

```
ValueError: balasan AI bukan JSON (content kosong)
```

Penanganan galat ini **sudah diperbaiki di `main.py`**. Sebelumnya, `content`
bernilai `null` membuat `re.search` melempar `TypeError: expected string or
bytes-like object, got 'NoneType'`, dan galat itu tertelan tanpa jejak. Sekarang
kondisi tersebut dikenali lebih dulu dan dilaporkan sebagai `ValueError` dengan
pesan yang jelas, lalu baris jatuh ke mode cadangan.

Yang belum tertangani: **durasi 280 detik untuk satu gambar**. Batas waktu
panggilan model belum memotong respons yang menggantung selama itu, sehingga
satu gambar bisa menahan seluruh proses. Ini perlu ditangani terpisah, dan
tercatat sebagai temuan.

## Berkas pendukung

| Berkas | Isi |
|---|---|
| `tests/sc_metrics.py` | Perhitungan akurasi, baseline, lift, macro-average, confusion matrix |
| `tests/sc_runner.py` | Runner: panggil model, simpan hasil per baris, tulis laporan |
| `tests/test_sc01_accuracy.py` | Test rumus metrik dan batas ruang lingkup |
| `results_per_row.csv` | Keluaran per gambar (tidak di-commit; berisi data transaksi) |

Hasil ditulis bertahap ke CSV setelah setiap gambar selesai diproses. Pada run
pertama di sesi sebelumnya proses sempat mati setelah puluhan panggilan API
berbayar; penulisan bertahap inilah yang menyelamatkan hasilnya.

## Kesimpulan

SC-01 belum tercapai dan tidak dapat dicapai tanpa lebih dulu menyelesaikan
masalah granularitas kategori. Kesimpulan ini berlaku pada kedelapan run,
terlepas dari selisih angka di antaranya yang berkisar antara 4,6% dan 15,4%.

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
