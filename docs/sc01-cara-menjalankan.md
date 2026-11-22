# Menjalankan evaluasi SC-01

Panduan ini menjelaskan cara menjalankan pengukuran akurasi kategori (SC-01) di
komputer lokal, mulai dari clone sampai membaca hasil.

## Ringkas

```bash
git clone https://github.com/Project-Rework-G3-AI/ai-finance-assistant.git
cd ai-finance-assistant

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # lalu isi 4 nilai (lihat bawah)

python3 tests/sc01_harness.py --download    # unduh 65 gambar
python3 tests/sc01_harness.py              # jalankan evaluasi
```

Hasil ada di `sc01-out/laporan.txt`, `sc01-out/metrik.json`, dan
`sc01-out/hasil_per_baris.csv`.

## Di mana 65 data itu disimpan

Data evaluasi **tidak ada di repo aplikasi**. Repo `ai-finance-assistant`
bersifat publik, sedangkan bukti transaksi berisi data keuangan perusahaan.

| Berkas | Lokasi | Repo |
|---|---|---|
| 118 gambar bukti transaksi | `final_project/Dataset PT Lokal Komoditi Indonesia/Bukti Transaksi Januari 2026/` | `NafisHandoko/ReworkAcademy` (**privat**) |
| Daftar 65 pasangan | `final_project/Dataset PT Lokal Komoditi Indonesia/sc01/sc01_pairs.csv` | `NafisHandoko/ReworkAcademy` (**privat**) |
| Harness dan test | `tests/sc01_*.py` | `ai-finance-assistant` (publik) |

Karena itu langkah `--download` mengunduh gambar dari repo privat memakai
`GITHUB_TOKEN`. Setelah gambar ada di disk, evaluasi berjalan sepenuhnya lokal
dan tidak lagi menyentuh GitHub.

Daftar 65 pasangan itu isinya apa:

| Kolom | Arti |
|---|---|
| `file` | nama berkas gambar bukti transaksi |
| `tanggal` | tanggal transaksi |
| `nominal_gambar` | nominal yang terbaca pada gambar |
| `nominal_acuan` | nominal pada baris Cash Report |
| `fee` | biaya transfer bila ada |
| `bank` | kantong (BNI, BRI, Jago, TUNAI) |
| `keterangan_gambar` | keterangan pada bukti |
| `kategori_acuan` | kategori yang ditetapkan Admin — inilah jawaban benar |
| `baris_xlsx` | nomor baris di file Excel asli, untuk penelusuran |

## Empat nilai yang harus diisi di `.env`

```ini
AI_API_KEY=sk-or-v1-...              # kunci OpenRouter
AI_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=deepseek/deepseek-v4.1-flash-1017

SC01_PAIRS=dataset/sc01/sc01_pairs.csv
SC01_IMAGES=dataset/Bukti Transaksi Januari 2026

GITHUB_TOKEN=ghp_...                 # hanya untuk --download
```

`SC01_PAIRS` adalah daftar pasangan; unduh sekali dari repo privat:

```bash
mkdir -p dataset/sc01
curl -L -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/NafisHandoko/ReworkAcademy/contents/final_project/Dataset%20PT%20Lokal%20Komoditi%20Indonesia/sc01/sc01_pairs.csv" \
  -H "Accept: application/vnd.github.raw" \
  -o dataset/sc01/sc01_pairs.csv
```

`SC01_IMAGES` boleh di mana saja. Bila dibiarkan kosong, `--download` akan
meminta diisi lebih dulu.

## Tiga cara menjalankan

### 1. Test cepat (gratis, di bawah 1 detik)

```bash
pytest
```

Menjalankan 9 test rumus metrik dan batas ruang lingkup. Tidak memanggil AI,
tidak butuh dataset. Ini yang dijalankan di CI.

### 2. Runner (cara utama untuk mengukur)

```bash
python3 tests/sc01_harness.py
```

Memanggil model asli pada 65 gambar, sekitar 15 menit dan biaya sekitar Rp1.100.
Hasil ditulis bertahap, jadi bila terputus tinggal jalankan ulang perintah yang
sama — yang sudah selesai tidak diulang.

Untuk sekadar menghitung ulang dari hasil yang sudah ada, tanpa biaya:

```bash
python3 tests/sc01_harness.py --metrics-only
```

Karena hasil antar-run bisa berbeda, untuk angka yang lebih dapat dipercaya
jalankan beberapa kali lalu lihat sebarannya:

```bash
python3 tests/sc01_harness.py --repeat 3
```

Setiap run disimpan di `sc01-out/run-N/`, dan ringkasan rentangnya di
`sc01-out/sebaran.txt`. Biaya dan waktu berlipat sesuai jumlah run.

### 3. Test model sebagai assertion (opsional)

```bash
SC01_RUN_MODEL=1 pytest -m sc01_model -v
```

Sama seperti runner, tetapi hasilnya berupa lulus/gagal terhadap target 85%.
Butuh opt-in karena berbayar dan lama; `pytest` biasa tidak akan menjalankannya.

## Keluaran

| Berkas | Isi |
|---|---|
| `sc01-out/laporan.txt` | Ringkasan, rincian per kategori, confusion matrix, daftar baris salah |
| `sc01-out/metrik.json` | Angka yang sama dalam bentuk JSON |
| `sc01-out/hasil_per_baris.csv` | Keluaran per gambar, termasuk nominal dan tanggal |

Folder `sc01-out/` masuk `.gitignore` karena berisi data transaksi.

## Kalau ada yang gagal

| Gejala | Sebab dan solusi |
|---|---|
| `SC01_PAIRS belum diisi di .env` | Isi variabelnya, atau pakai `--pairs` |
| `N dari 65 gambar tidak ada` | Jalankan `--download`, atau periksa `SC01_IMAGES` |
| `GITHUB_TOKEN kosong` | Tambahkan token dengan akses baca ke `NafisHandoko/ReworkAcademy` |
| `AI_API_KEY kosong` | Isi kunci; SC-01 mengukur model asli, bukan mock |
| `mode=mock` pada hasil | Panggilan AI gagal, lihat kolom `catatan` di CSV |
| Angka berbeda dari laporan | Model bersifat probabilistik; lihat catatan di bawah |

## Catatan tentang kestabilan angka

Kode sudah mengirim `temperature: 0` pada payload `_vision_extract()`, tetapi
hasilnya tidak dapat diulang. Empat eksekusi berturut-turut pada 65 gambar yang
sama memberi akurasi 15,4%, 13,8%, 12,3%, dan 4,6% — rentang 10,8 poin persen.

Keempatnya memakai kode identik dan semuanya bermode `vision`, tanpa galat dan
tanpa kategori kosong. Jadi ini bukan kegagalan teknis, melainkan model yang
memang menjawab berbeda-beda antar-run.

Penyebab yang paling mungkin adalah model penalaran (`deepseek-v4.1-flash-1017`)
yang tidak menjamin determinisme penuh lewat API pihak ketiga, ditambah tidak
adanya parameter `seed`.

Konsekuensinya penting untuk pelaporan: satu angka tidak cukup. Laporkan rentang
dari beberapa run, jangan satu hasil. Selisih sepuluh poin persen antar-run sudah
cukup untuk mengubah kesimpulan bila hanya satu run yang dilaporkan.

```bash
python3 tests/sc01_harness.py --repeat 3
```
