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

## Di mana data itu disimpan

Data evaluasi **tidak ada di repo aplikasi**. Repo `ai-finance-assistant` bersifat
publik, sedangkan bukti transaksi berisi data keuangan riil perusahaan. Data ada
di repo terpisah yang privat.

| Repo | Isi | Akses |
|---|---|---|
| `Project-Rework-G3-AI/rework-ai-finance-assistant-dataset` | Seluruh dataset: 118 foto, 3 Cash Report, 2 mutasi, SOP, dan `sc01/sc01_pairs.csv` | Publik |
| `Project-Rework-G3-AI/ai-finance-assistant` | Kode, test, dan dokumentasi | Publik |

Repo dataset sengaja dipisah dari repo aplikasi. Keduanya ada di organisasi
yang sama, dan repo dataset kini publik, jadi siapa pun bisa mengunduh datanya
tanpa perlu diundang atau memakai token.

### Token GitHub tidak lagi diperlukan

`--download` bekerja tanpa `GITHUB_TOKEN`. Berkas diambil lewat
`raw.githubusercontent.com`, yang tidak memakai kuota API. Ini perlu karena
kuota anonim API GitHub hanya 60 permintaan per jam, sedangkan satu kali unduh
butuh 66 permintaan.

`GITHUB_TOKEN` tetap dihormati bila diisi, dan berguna bila repo dataset suatu
saat dijadikan privat lagi. Untuk penggunaan normal, biarkan kosong.

### Catatan privasi

Repo dataset berisi data keuangan riil: nama pihak, nomor rekening, nominal, dan
bukti transfer. Jangan mengunggah ulang isinya ke layanan lain, dan jangan
menyebarkan tangkapan layarnya tanpa menyensor nomor rekening serta nama pihak.

### Isi repo dataset

| Folder | Jumlah | Isi |
|---|---|---|
| `Bukti Transaksi Januari 2026/` | 118 foto | Bukti transaksi |
| `Cash Report dan Mutasi Rekening/` | 5 berkas | 3 Cash Report (BNI, BRI, Operasional), 2 mutasi PDF |
| `SOP Keuangan/` | 3 berkas | Draf SOP |
| `sc01/sc01_pairs.csv` | 1 berkas | Daftar 65 pasangan gambar ke baris Cash Report |

Satu perintah `--download` mengambil daftar pasangan dulu, lalu 65 gambar yang
disebut di dalamnya. Setelah itu evaluasi berjalan sepenuhnya lokal dan tidak
lagi menyentuh GitHub.

Isi `sc01_pairs.csv`:

| Kolom | Arti |
|---|---|
| `file` | nama berkas gambar bukti transaksi |
| `tanggal` | tanggal transaksi |
| `nominal_gambar` | nominal yang terbaca pada gambar |
| `nominal_acuan` | nominal pada baris Cash Report |
| `fee` | biaya transfer bila ada |
| `bank` | kantor bank yang menangani |
| `keterangan_gambar` | keterangan pada bukti |
| `kategori_acuan` | kategori yang ditetapkan Admin, dipakai sebagai jawaban benar |
| `baris_xlsx` | nomor baris di berkas Excel Cash Report |

Dari 118 foto, hanya 65 yang bisa dipasangkan 1:1 ke baris Cash Report lewat
tanggal dan nominal. Sisanya tidak dipakai.

## Kalau sudah punya dataset sendiri

Bila kamu sudah meng-clone repo dataset, tidak perlu `--download`. Cukup arahkan
`SC01_PAIRS` dan `SC01_IMAGES` ke folder hasil clone:

```ini
SC01_PAIRS=../rework-ai-finance-assistant-dataset/sc01/sc01_pairs.csv
SC01_IMAGES=../rework-ai-finance-assistant-dataset/Bukti Transaksi Januari 2026
```

Atau tanpa menyunting `.env`, sebut langsung di perintah:

```bash
python3 tests/sc01_harness.py \
  --pairs ../rework-ai-finance-assistant-dataset/sc01/sc01_pairs.csv \
  --images "../rework-ai-finance-assistant-dataset/Bukti Transaksi Januari 2026"
```

Cara ini tidak butuh `GITHUB_TOKEN` sama sekali, karena tidak ada yang diunduh.

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
| `GITHUB_TOKEN kosong` | Isi token pribadimu; minta akses ke repo dataset bila belum diundang |
| `daftar pasangan belum ada` | Jalankan `--download` |
| `N dari 65 gambar tidak ada` | Jalankan `--download`; yang sudah ada tidak diulang |
| `AI_API_KEY kosong` | Isi kunci; SC-01 mengukur model asli, bukan mock |
| `mode=mock` pada hasil | Panggilan AI gagal; lihat kolom `catatan` di CSV |
| Angka berbeda dari laporan | Model bersifat probabilistik; lihat catatan di bawah |

## Catatan tentang kestabilan angka

Kode sudah mengirim `temperature: 0` pada payload `_vision_extract()`, tetapi
hasilnya tidak dapat diulang. Enam eksekusi berturut-turut pada 65 gambar yang
sama memberi akurasi 15,4%, 13,8%, 12,3%, 4,6%, 7,7%, dan 10,8% — rentang 10,8
poin persen.

Keenam run memakai kode identik dan hampir semuanya bermode `vision`. Pada run 5
dan run 6 ada 1 dan 2 baris yang jatuh ke `mock` karena model membalas
`content: null`, yang memicu galat di `main.py` baris 135 lalu ditangkap sebagai
kegagalan. Baris seperti itu tercatat salah karena kategorinya kosong, jadi ikut
menekan angka. Sebagian variasi berasal dari model, sebagian kecil dari jalur
galat itu.

Satu baris juga pernah memakan 515 detik karena model berpikir sangat panjang.
Timeout 90 detik di `_vision_extract()` adalah timeout per operasi baca, bukan
batas total, sehingga baris seperti itu tidak diputus. Untuk 65 gambar, sediakan
waktu 10 sampai 25 menit.

Penyebab yang paling mungkin adalah model penalaran (`deepseek-v4.1-flash-1017`)
yang tidak menjamin determinisme penuh lewat API pihak ketiga, ditambah tidak
adanya parameter `seed`.

Konsekuensinya penting untuk pelaporan: satu angka tidak cukup. Laporkan rentang
dari beberapa run, jangan satu hasil. Selisih sepuluh poin persen antar-run sudah
cukup untuk mengubah kesimpulan bila hanya satu run yang dilaporkan.

```bash
python3 tests/sc01_harness.py --repeat 3
```
