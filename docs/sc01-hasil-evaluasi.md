# SC-01 — Hasil evaluasi akurasi kategori

Dokumen ini mencatat hasil pengukuran kriteria keberhasilan **SC-01** pada BRD:
akurasi usulan kategori dibandingkan kategori yang ditetapkan Admin, dengan
target minimal 85%.

Angka di bawah berasal dari satu eksekusi nyata, bukan perkiraan. Perintah dan
berkas pendukungnya disertakan agar hasil bisa diperiksa ulang.

## Ringkasan

| Metrik | Nilai |
|---|---|
| Total pasangan diuji | 65 |
| Benar | 10 |
| **Akurasi** | **15,4%** |
| Baseline kelas mayoritas | 75,4% (`Transfer Antar Bank`, 49 dari 65) |
| **Lift atas baseline** | **−60,0%** |
| Macro-average recall | 52,9% (5 kategori) |
| Target BRD | 85% |
| Status | **Belum tercapai** |

Akurasi 15,4% berada jauh di bawah baseline 75,4%. Artinya model bukan hanya
belum mencapai target, tetapi lebih buruk daripada menjawab `Transfer Antar Bank`
untuk setiap gambar tanpa melihat isinya.

## Cara pengukuran

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

Perintah yang dipakai:

```bash
python3 tests/sc01_harness.py \
    --set-uji /path/set_uji_1to1.csv \
    --img-dir /path/gambar \
    --out /path/hasil
```

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
masalah granularitas kategori. Dua langkah yang masuk akal, dan keduanya perlu
keputusan pemilik produk:

1. **Menyamakan granularitas.** Tetapkan satu tingkat kerincian untuk kolom
   kategori, lalu ukur ulang. Bila acuan memakai tingkat rinci, model yang
   sekarang sudah menjawab rinci berpeluang besar lolos 85%.
2. **Mengukur pada baris yang punya padanan rinci.** Batasi SC-01 pada baris
   yang acuannya bukan `Transfer Antar Bank`, lalu laporkan sisanya terpisah
   sebagai kasus yang tidak dapat dinilai.

Yang tidak boleh dilakukan adalah melaporkan angka 15,4% tanpa menyebut baseline
75,4%, karena pembaca akan menyimpulkan modelnya hampir benar padahal kalah dari
tebakan konstan.
