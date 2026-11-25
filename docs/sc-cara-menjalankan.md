# Menjalankan evaluasi kriteria keberhasilan

Panduan ini menjelaskan cara mengukur kriteria keberhasilan (SC) pada BRD di
komputer lokal, mulai dari clone sampai membaca hasil. Satu set data dan satu
runner dipakai untuk semua kriteria; yang berbeda hanya cara menilainya.

Kriteria yang sudah bisa diukur:

| Kriteria | Yang diukur | Status |
|---|---|---|
| SC-01 | Akurasi usulan kategori | sudah |
| SC-02 | Kelengkapan field wajib | sudah |
| SC-03 | Waktu proses sampai tersimpan | sudah, perlu kredensial Google |
| SC-04 | Biaya per gambar | sudah, perlu kredensial + kurs |
| SC-05 | Duplikat ditolak | belum |
| SC-06 | Semua kolom wajib terpetakan | belum |
| SC-07 | Waktu satu periode vs manual | belum, tidak dapat diotomasi |

## Ringkas

```bash
git clone https://github.com/Project-Rework-G3-AI/ai-finance-assistant.git
cd ai-finance-assistant
git checkout test/integration-testing

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # isi AI_API_KEY, sesuaikan AI_BASE_URL/AI_MODEL

python3 tests/sc_runner.py --download      # unduh data (sekali saja)
python3 tests/sc_runner.py                 # ukur semua kriteria
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
| `SC_PAIRS` | `dataset/pairs.csv` |
| `SC_IMAGES` | `dataset/Bukti Transaksi Januari 2026` |

Daftar pasangan dulu bernama `sc01/sc01_pairs.csv`, yang menyiratkan berkas itu
hanya dipakai SC-01. Sekarang namanya `pairs.csv` di akar repo dataset, karena
kolomnya memasok acuan beberapa kriteria sekaligus: kategori untuk SC-01 dan
SC-02, serta tanggal, nominal, kantong, dan keterangan untuk SC-02.

## Di mana data itu disimpan

Data evaluasi **tidak ada di repo aplikasi**. Repo `ai-finance-assistant` berisi
kode, sedangkan bukti transaksi berisi data keuangan riil perusahaan. Data ada
di repo terpisah.

| Repo | Isi | Akses |
|---|---|---|
| `Project-Rework-G3-AI/rework-ai-finance-assistant-dataset` | Seluruh dataset: 118 foto, 3 Cash Report, 2 mutasi, SOP, dan `pairs.csv` | Publik |
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
| `pairs.csv` | 1 berkas | Daftar 65 pasangan gambar ke baris Cash Report |

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
python3 tests/sc_runner.py                 # semua kriteria (sama dengan --all)
python3 tests/sc_runner.py --sc01          # SC-01 saja
python3 tests/sc_runner.py --sc02          # SC-02 saja
python3 tests/sc_runner.py --sc03          # SC-03 saja (melaporkan hasil ukur)
python3 tests/sc_runner.py --sc04          # SC-04 saja (melaporkan biaya)
python3 tests/sc_runner.py --all           # semua kriteria, eksplisit
```

**SC-03 berbeda dari SC-01 dan SC-02.** Waktu tidak tersimpan di hasil
ekstraksi, jadi tidak bisa dihitung ulang dari CSV. `--sc03` hanya
**merangkum** sampel yang sudah ada di `sc-out/sc03_samples.csv`. Untuk
mengukurnya, jalankan harness pengukur lebih dulu:

```bash
python3 tests/_sc03_run.py             # melanjutkan yang belum terukur
python3 tests/_sc03_run.py --restart   # ukur ulang dari nol
python3 tests/_sc03_run.py --limit 5   # coba cepat pada 5 gambar
```

Pengukuran SC-03 menulis baris sungguhan ke Google Sheets, karena itu
dijalankan di folder **sandbox**, bukan folder Cash Report perusahaan. Lihat
`docs/sc03-hasil-evaluasi.md`.

**SC-04 juga berbeda.** Jumlah token tidak tersimpan di hasil ekstraksi, jadi
biaya tidak bisa dihitung dari CSV hasil. `--sc04` merangkum
`sc-out/sc04_samples.csv` yang berisi token per gambar. Ukur dulu:

```bash
python3 tests/_sc04_run.py --usd-idr 18227
python3 tests/_sc04_run.py --limit 5 --usd-idr 18227
```

Tarif model disunting di satu tempat, di bagian atas `tests/sc04_cost.py`:

```python
PRICE_PROMPT_USD = 0.00000015
PRICE_COMPLETION_USD = 0.0000006
```

Biaya tidak pernah disimpan, selalu diturunkan dari token x tarif x kurs. Jadi
mengubah tarif atau kurs langsung mengubah laporan tanpa mengukur ulang. Lihat
`docs/sc04-hasil-evaluasi.md`.

Tanpa flag berarti semua kriteria yang tersedia. Ini disengaja: kriteria
saling setara, jadi tidak ada alasan menjadikan salah satunya bawaan. Ketiga
flag itu saling eksklusif, dan menggabungkannya akan ditolak argparse.

Satu lintasan memanggil model untuk 65 gambar. Sekitar 10 sampai 20 menit,
tergantung kecepatan respons model. Hasil ditulis bertahap, jadi bila terputus
tinggal jalankan perintah yang sama — yang sudah selesai tidak diulang.

Menambah kriteria tidak menambah biaya, karena semuanya membaca keluaran
ekstraksi yang sama. Memisahkan lintasan hanya akan menggandakan biaya tanpa
menambah informasi.

Menghitung ulang dari hasil yang sudah ada, tanpa biaya:

```bash
python3 tests/sc_runner.py --metrics-only
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

## Hasil lama dipakai lagi, bukan dihitung ulang

Runner menyimpan hasil per gambar ke `sc-out/results_per_row.csv` dan
melanjutkan dari situ. Ini disengaja: kalau run terputus di gambar ke-40,
menjalankan ulang tidak perlu mengulang 39 gambar yang sudah selesai.

Konsekuensinya, **menjalankan perintah yang sama dua kali tidak memanggil model
lagi pada run kedua**. Run kedua selesai dalam hitungan detik dan langsung
mencetak angka dari run pertama. Itu bukan tanda modelnya cepat.

Supaya tidak salah tafsir, runner sekarang mengumumkannya:

```
============================================================
HASIL LAMA DIPAKAI LAGI — TIDAK ADA PEMANGGILAN MODEL BARU
============================================================
  sudah ada di CSV : 65 dari 65 gambar
  akan diproses    : 0 gambar
  panggilan model  : 0 — angka di bawah adalah hasil run sebelumnya

  Untuk benar-benar menghitung ulang, pakai --restart.
  Untuk sekadar melihat angka tanpa AI, pakai --metrics-only.
============================================================
```

Asal angka juga dicatat di `sc-out/source.json` dan muncul di kepala setiap
laporan:

```
Sumber data: dihitung 2026-11-24 12:44:57 UTC dengan 65 panggilan model (google/gemini-3.8-flash).
```

atau, kalau tidak ada model yang dipanggil:

```
Sumber data: hasil run sebelumnya, dihitung 2026-11-24 11:46:00 UTC. Tidak ada panggilan model saat laporan ini dibuat.
```

Jadi angka dari run kemarin tidak bisa dikutip sebagai hasil hitung baru tanpa
ketahuan.

### Kapan pakai yang mana

| Perintah | Panggilan model | Kegunaan |
|---|---|---|
| `sc_runner.py` | hanya untuk gambar yang belum ada | melanjutkan run yang terputus |
| `sc_runner.py --restart` | semua gambar | mengukur ulang dari nol |
| `sc_runner.py --metrics-only` | tidak ada | mengubah cara menilai tanpa bayar lagi |

`--restart` menghapus dan menulis ulang `results_per_row.csv`, jadi jangan
dipakai kalau hasil lama masih dibutuhkan.

### Hasil dari set data lain ditolak

CSV hasil terikat ke satu daftar pasangan. Kalau CSV dibuat dengan pasangan
berbeda, angkanya tidak sah untuk set sekarang, jadi runner berhenti:

```
hasil di sc-out/results_per_row.csv dibuat dengan pasangan berbeda: 63 berkas
tidak ada di daftar sekarang (contoh: photo_2026-01-01_17-06-05.jpg).
Hapus berkas itu, atau jalankan dengan --restart.
```

## Keluaran

| Berkas | Isi |
|---|---|
| `sc-out/sc01_report.txt` | SC-01: ringkasan, rincian per kategori, confusion matrix, daftar baris salah |
| `sc-out/sc01_metrics.json` | SC-01 dalam bentuk JSON |
| `sc-out/sc02_report.txt` | SC-02: kelengkapan dan kecocokan per field wajib |
| `sc-out/sc02_metrics.json` | SC-02 dalam bentuk JSON |
| `sc-out/sc03_report.txt` | SC-03: sebaran waktu dan pecahan per tahap |
| `sc-out/sc03_metrics.json` | SC-03 dalam bentuk JSON |
| `sc-out/sc03_samples.csv` | SC-03: satu baris per gambar, termasuk pecahan tahap |
| `sc-out/sc04_report.txt` | SC-04: biaya per gambar dan token |
| `sc-out/sc04_metrics.json` | SC-04 dalam bentuk JSON |
| `sc-out/sc04_samples.csv` | SC-04: token per gambar (tanpa biaya) |
| `sc-out/results_per_row.csv` | Keluaran per gambar, termasuk nominal, tanggal, kantong, arah |

Folder `sc-out/` dan `dataset/` masuk `.gitignore` karena berisi data transaksi.
Jangan hapus baris itu dari `.gitignore`.

## SC-01: akurasi usulan kategori

**Pertanyaan:** apakah kategori yang dipilih sistem sama dengan kategori yang
ditetapkan Admin?

**Target BRD:** minimal 85%.

**Cara menilai:** dibandingkan langsung per baris dengan `kategori_acuan` di
`pairs.csv`.

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

| Field | Acuan tersedia di `pairs.csv` |
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
