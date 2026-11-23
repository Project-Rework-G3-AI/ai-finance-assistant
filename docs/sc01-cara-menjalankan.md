# Menjalankan evaluasi SC-01

Panduan ini menjelaskan cara menjalankan pengukuran akurasi kategori (SC-01) di
komputer lokal, mulai dari clone sampai membaca hasil.

## Ringkas

```bash
git clone https://github.com/Project-Rework-G3-AI/ai-finance-assistant.git
cd ai-finance-assistant
git checkout test/sc01-kategori-accuracy

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # isi 4 nilai, lihat bawah

python3 tests/sc01_harness.py --download    # unduh data (sekali saja)
python3 tests/sc01_harness.py              # jalankan evaluasi
```

Hasil ada di `sc01-out/laporan.txt`, `sc01-out/metrik.json`, dan
`sc01-out/hasil_per_baris.csv`.

## Empat nilai yang harus diisi di `.env`

Buka `.env`, isi empat baris ini. Sisanya boleh dibiarkan apa adanya.

```ini
AI_API_KEY=sk-or-v1-...              # kunci OpenRouter
AI_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=deepseek/deepseek-v4.1-flash-1017

GITHUB_TOKEN=ghp_...                 # hanya untuk --download
```

`AI_API_KEY` dibutuhkan karena SC-01 mengukur model asli, bukan mock.
`GITHUB_TOKEN` butuh akses baca ke repo dataset privat. Bila tokennya tidak
punya akses, `--download` akan berhenti dengan pesan yang menyebut repo mana
yang gagal diakses.

`SC01_PAIRS` dan `SC01_IMAGES` **tidak perlu diisi**. Keduanya punya nilai
bawaan yang cocok dengan hasil `--download`:

| Kunci | Nilai bawaan |
|---|---|
| `SC01_PAIRS` | `dataset/sc01/sc01_pairs.csv` |
| `SC01_IMAGES` | `dataset/Bukti Transaksi Januari 2026` |

Isi hanya bila ingin menaruh data di tempat lain.

## Di mana 65 data itu disimpan

Data evaluasi **tidak ada di repo aplikasi**. Repo `ai-finance-assistant`
bersifat publik, sedangkan bukti transaksi berisi data keuangan perusahaan.
Datanya ada di repo terpisah yang privat.

| Berkas | Lokasi | Repo |
|---|---|---|
| 118 gambar bukti transaksi | `final_project/Dataset PT Lokal Komoditi Indonesia/Bukti Transaksi Januari 2026/` | `NafisHandoko/ReworkAcademy` (privat) |
| Daftar 65 pasangan | `final_project/Dataset PT Lokal Komoditi Indonesia/sc01/sc01_pairs.csv` | `NafisHandoko/ReworkAcademy` (privat) |
| Harness dan test | `tests/sc01_*.py` | `ai-finance-assistant` (publik) |

Satu perintah `--download` mengambil keduanya: daftar pasangan dulu, lalu 65
gambar yang disebutkan di dalamnya. Setelah itu evaluasi berjalan sepenuhnya
lokal dan tidak lagi menyentuh GitHub.

Isi daftar pasangan:

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

## Tiga cara menjalankan

### 1. Test cepat (gratis, sekitar 1 detik)

```bash
pytest
```

Menjalankan 9 test rumus metrik dan batas ruang lingkup. Tidak memanggil AI dan
tidak butuh dataset. Ini yang dijalankan di CI.

### 2. Runner (cara utama untuk mengukur)

```bash
python3 tests/sc01_harness.py
```

Memanggil model asli pada 65 gambar. Sekitar 10 sampai 20 menit, tergantung
kecepatan respons model, dengan biaya sekitar Rp1.100. Hasil ditulis bertahap,
jadi bila terputus tinggal jalankan perintah yang sama — yang sudah selesai
tidak diulang.

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

Sama seperti runner, tetapi hasilnya berupa lulus atau gagal terhadap target
85%. Butuh opt-in karena berbayar dan lama; `pytest` biasa tidak akan
menjalankannya.

## Keluaran

| Berkas | Isi |
|---|---|
| `sc01-out/laporan.txt` | Ringkasan, rincian per kategori, confusion matrix, daftar baris salah |
| `sc01-out/metrik.json` | Angka yang sama dalam bentuk JSON |
| `sc01-out/hasil_per_baris.csv` | Keluaran per gambar, termasuk nominal dan tanggal |

Folder `sc01-out/` dan `dataset/` masuk `.gitignore` karena berisi data
transaksi. Jangan hapus baris itu dari `.gitignore`.

## Kalau ada yang gagal

| Gejala | Sebab dan solusi |
|---|---|
| `GITHUB_TOKEN kosong` | Isi token dengan akses baca ke `NafisHandoko/ReworkAcademy` |
| `daftar pasangan belum ada` | Jalankan `--download` |
| `N dari 65 gambar tidak ada` | Jalankan `--download`; yang sudah ada tidak diulang |
| `AI_API_KEY kosong` | Isi kunci; SC-01 mengukur model asli, bukan mock |
| `mode=mock` pada hasil | Panggilan AI gagal; lihat kolom `catatan` di CSV |
| Angka berbeda dari laporan | Model bersifat probabilistik; lihat catatan di bawah |

## Catatan tentang kestabilan angka

Kode sudah mengirim `temperature: 0` pada payload `_vision_extract()`, tetapi
hasilnya tidak dapat diulang. Lima eksekusi berturut-turut pada 65 gambar yang
sama memberi akurasi 15,4%, 13,8%, 12,3%, 4,6%, dan 7,7% — rentang 10,8 poin
persen.

Kelima run memakai kode identik dan hampir semuanya bermode `vision`. Satu baris
pada run terakhir jatuh ke `mock` karena model membalas `content: null`, yang
memicu galat di `main.py` baris 135 lalu ditangkap sebagai kegagalan. Jadi
sebagian variasi berasal dari model, sebagian kecil dari jalur galat itu.

Penyebab yang paling mungkin adalah model penalaran (`deepseek-v4.1-flash-1017`)
yang tidak menjamin determinisme penuh lewat API pihak ketiga, ditambah tidak
adanya parameter `seed`.

Konsekuensinya penting untuk pelaporan: satu angka tidak cukup. Laporkan rentang
dari beberapa run, jangan satu hasil. Selisih sepuluh poin persen antar-run sudah
cukup untuk mengubah kesimpulan bila hanya satu run yang dilaporkan.

```bash
python3 tests/sc01_harness.py --repeat 3
```
