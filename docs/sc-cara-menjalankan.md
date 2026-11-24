# Menjalankan evaluasi kriteria keberhasilan

Panduan ini menjelaskan cara mengukur kriteria keberhasilan (SC) pada BRD di
komputer lokal, mulai dari clone sampai membaca hasil. Satu set data dan satu
runner dipakai untuk semua kriteria; yang berbeda hanya cara menilainya.

Kriteria yang sudah bisa diukur:

| Kriteria | Yang diukur | Status |
|---|---|---|
| SC-01 | Akurasi usulan kategori | sudah |
| SC-02 | Kelengkapan field wajib | sudah |
| SC-03 | Waktu proses sampai tersimpan | belum |
| SC-04 | Biaya per gambar | belum |
| SC-05 | Duplikat ditolak | belum |
| SC-06 | Semua kolom wajib terpetakan | belum |
| SC-07 | Waktu satu periode vs manual | belum, tidak dapat diotomasi |

## Ringkas

```bash
git clone https://github.com/Project-Rework-G3-AI/ai-finance-assistant.git
cd ai-finance-assistant
git checkout test/success-criteria

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # isi AI_API_KEY, sesuaikan AI_BASE_URL/AI_MODEL

python3 tests/sc_runner.py --download      # unduh data (sekali saja)
python3 tests/sc_runner.py --all           # ukur SC-01 dan SC-02 sekaligus
```

Hasil ada di `sc-out/`.

## Empat nilai yang diisi di `.env`

```ini
AI_API_KEY=sk-or-v1-...              # kunci OpenRouter
AI_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=google/gemini-3.8-flash

GITHUB_TOKEN=                        # biarkan kosong, tidak diperlukan
```

`SC_PAIRS` dan `SC_IMAGES` **tidak perlu diisi**. Keduanya punya nilai bawaan
yang cocok dengan hasil `--download`:

| Kunci | Nilai bawaan |
|---|---|
| `SC_PAIRS` | `dataset/sc01/sc01_pairs.csv` |
| `SC_IMAGES` | `dataset/Bukti Transaksi Januari 2026` |

Nama folder `sc01/` di repo dataset dipertahankan karena berkasnya sudah dipakai
bersama, tetapi isinya dipakai oleh semua kriteria, bukan hanya SC-01.

## Di mana data itu disimpan

Data evaluasi **tidak ada di repo aplikasi**. Repo `ai-finance-assistant` berisi
kode, sedangkan bukti transaksi berisi data keuangan riil perusahaan. Data ada
di repo terpisah.

| Repo | Isi | Akses |
|---|---|---|
| `Project-Rework-G3-AI/rework-ai-finance-assistant-dataset` | Seluruh dataset: 118 foto, 3 Cash Report, 2 mutasi, SOP, dan `sc01/sc01_pairs.csv` | Publik |
| `Project-Rework-G3-AI/ai-finance-assistant` | Kode, test, dan dokumentasi | Publik |

### Token GitHub tidak diperlukan

`--download` bekerja tanpa `GITHUB_TOKEN`. Berkas diambil lewat
`raw.githubusercontent.com`, yang tidak memakai kuota API. Ini perlu karena
kuota anonim API GitHub hanya 60 permintaan per jam, sedangkan satu kali unduh
butuh 66 permintaan.

`GITHUB_TOKEN` tetap dihormati bila diisi, dan dipakai otomatis bila repo dataset
suatu saat dijadikan privat lagi.

### Catatan privasi

Repo dataset berisi data keuangan riil: nama pihak, nomor rekening, nominal, dan
bukti transfer. Jangan mengunggah ulang isinya ke layanan lain, dan jangan
menyebarkan tangkapan layarnya tanpa menyensor nomor rekening serta nama pihak.

### Isi repo dataset

| Folder | Jumlah | Isi |
|---|---|---|
| `Bukti Transaksi Januari 2026/` | 118 foto | Bukti transaksi |
| `Cash Report dan Mutasi Rekening/` | 5 berkas | 3 Cash Report, 2 mutasi PDF |
| `SOP Keuangan/` | 3 berkas | Draf SOP |
| `sc01/sc01_pairs.csv` | 1 berkas | Daftar 65 pasangan gambar ke baris Cash Report |

Dari 118 foto, hanya 65 yang bisa dipasangkan 1:1 ke baris Cash Report lewat
tanggal dan nominal. Sisanya tidak punya acuan, sehingga hanya bisa dipakai
untuk mengukur keterbacaan, bukan kecocokan.

## Cara menjalankan

### Test cepat (gratis, sekitar 1 detik)

```bash
pytest
```

Menjalankan test rumus metrik SC-01, aturan penilaian SC-02, validasi dataset,
dan batas ruang lingkup. Tidak memanggil AI, tidak butuh jaringan, tidak butuh
dataset. Ini yang aman dijalankan di CI.

### Runner (cara utama untuk mengukur)

```bash
python3 tests/sc_runner.py --all           # SC-01 dan SC-02 sekaligus
python3 tests/sc_runner.py                 # SC-01 saja
python3 tests/sc_runner.py --sc02          # SC-02 saja
```

Satu lintasan memanggil model untuk 65 gambar. Sekitar 10 sampai 20 menit,
tergantung kecepatan respons model. Hasil ditulis bertahap, jadi bila terputus
tinggal jalankan perintah yang sama — yang sudah selesai tidak diulang.

`--all` tidak menambah biaya, karena SC-01 dan SC-02 membaca keluaran ekstraksi
yang sama. Memisahkan lintasan hanya akan menggandakan biaya tanpa menambah
informasi.

Menghitung ulang dari hasil yang sudah ada, tanpa biaya:

```bash
python3 tests/sc_runner.py --metrics-only --all
```

Karena hasil antar-run bisa berbeda, untuk angka yang lebih dapat dipercaya
jalankan beberapa kali lalu lihat sebarannya:

```bash
python3 tests/sc_runner.py --repeat 3
```

Setiap run disimpan di `sc-out/run-N/`, dan ringkasan rentangnya di
`sc-out/spread.txt`. Biaya dan waktu berlipat sesuai jumlah run.

### Test model sebagai assertion (opsional)

```bash
SC_RUN_MODEL=1 pytest -m sc_model -v
```

Menjalankan evaluasi sebagai lulus atau gagal terhadap target BRD. Butuh opt-in
karena berbayar dan lama; `pytest` biasa tidak akan menjalankannya.

## Keluaran

| Berkas | Isi |
|---|---|
| `sc-out/report.txt` | SC-01: ringkasan, rincian per kategori, confusion matrix, daftar baris salah |
| `sc-out/metrics.json` | SC-01 dalam bentuk JSON |
| `sc-out/sc02_report.txt` | SC-02: kelengkapan dan kecocokan per field wajib |
| `sc-out/sc02_metrics.json` | SC-02 dalam bentuk JSON |
| `sc-out/results_per_row.csv` | Keluaran per gambar, termasuk nominal, tanggal, kantong, arah |

Folder `sc-out/` dan `dataset/` masuk `.gitignore` karena berisi data transaksi.
Jangan hapus baris itu dari `.gitignore`.

## SC-01: akurasi usulan kategori

**Pertanyaan:** apakah kategori yang dipilih sistem sama dengan kategori yang
ditetapkan Admin?

**Target BRD:** minimal 85%.

**Cara menilai:** dibandingkan langsung per baris dengan `kategori_acuan` di
`sc01_pairs.csv`.

Tiga angka dilaporkan bersamaan, karena satu angka saja menyesatkan:

| Angka | Arti |
|---|---|
| akurasi | benar / total |
| baseline | proporsi kelas terbanyak; batas bawah yang harus dilewati model |
| macro-average recall | rata-rata per kategori, agar kategori jarang tidak tertutup |

Selisih akurasi terhadap baseline disebut lift. Lift negatif berarti model kalah
dari tebakan konstan, sekalipun akurasinya terlihat tinggi.

## SC-02: kelengkapan field wajib

**Pertanyaan:** apakah field wajib benar-benar terbaca dari gambar?

**Target BRD:** minimal 90% field wajib terbaca benar pada 118 gambar uji.

**Lima field wajib:** tanggal, nominal, kantong, arah, kategori.

### Jebakan utama: nilai bawaan

`main.extract` mengisi nilai bawaan ketika model gagal membaca:

```python
"tanggal": data.get("tanggal") or datetime.now()...   # -> hari ini
"arah": arah if arah in (...) else "keluar"           # -> keluar
# bank kosong -> CR_DEFAULT_BANK
```

Kalau kelengkapan diukur dengan "field kosong atau tidak", hasilnya akan
**mendekati 100% padahal model gagal membaca**. Karena itu penilaian memakai
tiga sumber, berurutan dari yang paling dapat dipercaya:

1. **`catatan`** — `main.py` menulis `"nominal tidak terbaca — isi manual"` dan
   sejenisnya. Ini sinyal paling langsung.
2. **`mode`** — `mock` berarti model tidak dipanggil atau gagal total, jadi
   tidak ada yang terbaca.
3. **acuan** — bila nilai acuan tersedia, hasil dibandingkan langsung.

Karena itu SC-02 melaporkan dua angka berbeda:

| Angka | Arti |
|---|---|
| kelengkapan | field terbaca, tanpa penanda gagal baca, bukan mode mock |
| akurasi | terbaca **dan** nilainya cocok dengan acuan |

Selisih keduanya menunjukkan field yang terbaca tetapi salah nilainya.

### Cakupan acuan

| Field | Acuan tersedia di `sc01_pairs.csv` |
|---|---|
| tanggal | ya, `tanggal` |
| nominal | ya, `nominal_acuan` |
| kantong | ya, `bank` (62 dari 65 terisi) |
| kategori | ya, `kategori_acuan` |
| arah | **tidak** — hanya keterbacaan yang dinilai |

Untuk 118 gambar di luar 65 pasangan, hanya keterbacaan yang bisa diukur.

### Kenapa hasil SC-02 tidak mengikuti SC-01

Keduanya mengukur hal berbeda. Model bisa membaca tanggal, nominal, dan
keterangan dengan tepat hampir selalu, tetapi tetap salah memilih granularitas
kategori. Hasil SC-01 yang rendah karena itu tidak meramalkan SC-02.

## Kalau ada yang gagal

| Gejala | Sebab dan solusi |
|---|---|
| `daftar pasangan belum ada` | Jalankan `--download` |
| `N dari 65 gambar tidak ada` | Jalankan `--download`; yang sudah ada tidak diulang |
| `AI_API_KEY kosong` | Isi kunci; evaluasi mengukur model asli, bukan mock |
| `mode=mock` pada hasil | Panggilan AI gagal; lihat kolom `note` di CSV |
| `HTTP 401` | `AI_API_KEY` tidak cocok dengan `AI_BASE_URL` |
| `HTTP 404` pada model | `AI_MODEL` sudah tidak tersedia; pilih model lain |
| Angka berbeda dari laporan | Model bersifat probabilistik; lihat catatan di bawah |

## Catatan tentang kestabilan angka

Kode sudah mengirim `temperature: 0` pada payload `_vision_extract()`, tetapi
hasilnya tidak dapat diulang. Enam eksekusi SC-01 berturut-turut pada 65 gambar
yang sama memberi akurasi 15,4%, 13,8%, 12,3%, 4,6%, 7,7%, dan 10,8% — rentang
10,8 poin persen.

Sebagian variasi berasal dari model, sebagian kecil dari jalur galat: pada
beberapa run ada baris yang jatuh ke `mock` karena model membalas
`content: null`, yang memicu galat di `main.py` baris 135. Baris seperti itu
tercatat gagal, jadi ikut menekan angka.

Satu baris juga pernah memakan 515 detik karena model berpikir sangat panjang.
Timeout 90 detik di `_vision_extract()` adalah timeout per operasi baca, bukan
batas total, sehingga baris seperti itu tidak diputus. Untuk 65 gambar, sediakan
waktu 10 sampai 25 menit.

Konsekuensinya untuk pelaporan: satu angka tidak cukup. Laporkan rentang dari
beberapa run, jangan satu hasil.
