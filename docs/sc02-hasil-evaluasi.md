# SC-02 — Hasil evaluasi kelengkapan field wajib

Dokumen ini mencatat hasil pengukuran kriteria keberhasilan **SC-02** pada BRD:
persentase field wajib yang **terbaca benar** dari gambar bukti transaksi.

**Target BRD:** minimal 90% field wajib terbaca benar pada 118 gambar uji
Januari 2026.

## Ringkasan

| Ukuran | Hasil | Target | Status |
|---|---|---|---|
| Kelengkapan (field terbaca) | **98,2%** | 90% | tercapai |
| Kecocokan (terbaca **benar**) | **72,5%** | 90% | **belum tercapai** |
| Baris dengan 5/5 field lengkap | **59 dari 65** | — | — |

Angka yang dipakai menilai target adalah **kecocokan 72,5%**, karena BRD
menyebut "terbaca **benar**", bukan sekadar "terisi". Kelengkapan 98,2%
dilaporkan berdampingan karena keduanya menjelaskan hal berbeda: model hampir
selalu membaca sesuatu, tetapi tidak selalu nilainya tepat.

## Rincian per field

| Field | Terbaca | Kelengkapan | Cocok | Akurasi | Nilai bawaan terpakai |
|---|---|---|---|---|---|
| Tanggal | 65/65 | 100,0% | 65 | **100,0%** | 0 |
| Nominal | 65/65 | 100,0% | 64 | **98,5%** | 0 |
| Kantong | 59/65 | 90,8% | 54 | **87,1%** | 6 |
| Arah | 65/65 | 100,0% | — | tidak dinilai | 0 |
| Kategori | 65/65 | 100,0% | 3 | **4,6%** | 0 |

Kolom "cocok" untuk kantong berpenyebut 62, bukan 65, karena hanya 62 baris di
`sc01_pairs.csv` yang punya acuan `bank`. Kolom "arah" tidak dinilai karena
dataset tidak menyediakan acuan arah.

## Temuan utama

### Kategori menyeret seluruh angka

Kalau kelima field dirata-ratakan apa adanya, hasilnya 72,5% dan target tidak
tercapai. Tetapi penyebabnya **satu field saja**:

| Perhitungan | Hasil |
|---|---|
| Semua field beracuan (tanggal, nominal, kantong, kategori) | **72,5%** |
| Tanpa kategori (tanggal, nominal, kantong) | **95,2%** |

Tanggal, nominal, dan kantong semuanya di atas 87%. Kategori 4,6%. Jadi
ekstraksi **field administratif** sebenarnya sudah memenuhi target; yang gagal
adalah pemilihan kategori.

Ini penting karena kategori sudah punya kriterianya sendiri, yaitu SC-01. Kalau
kategori ikut dihitung di SC-02, satu akar masalah yang sama membuat dua
kriteria gagal sekaligus, dan laporan seolah menunjukkan dua kegagalan terpisah
padahal hanya satu.

**Rekomendasi pelaporan:** laporkan SC-02 tanpa kategori sebagai angka utama,
lalu sebutkan kategori sebagai temuan SC-01. Jangan hapus kategori dari SC-02
tanpa menyebutkannya — pembaca perlu tahu bahwa field itu diukur di tempat lain.

### Enam baris gagal membaca kantong

Kantong terbaca di 59 dari 65 gambar. Enam sisanya memakai nilai bawaan
`CR_DEFAULT_BANK`, dan kode menandainya dengan catatan "kantong tidak terbaca —
pakai default". Ini terdeteksi karena penilaian memakai penanda `catatan`, bukan
nilai akhir field.

Kalau penilaian hanya melihat "field kosong atau tidak", keenam baris itu akan
terhitung berhasil, karena `main.py` sudah mengisi nilainya. Itu akan membuat
kelengkapan kantong tampak 100%.

Dari 59 yang terbaca, 54 cocok dengan acuan (87,1%). Selisih 5 baris berarti
model membaca kantong yang berbeda dari yang tercatat — kemungkinan besar terbaca
dari gambar, tetapi bukan kantong yang dimaksud baris Cash Report.

### Tanggal dan nominal hampir sempurna

Tanggal 100%, nominal 98,5%. Satu baris nominal tidak cocok, kemungkinan karena
nominal yang tertera di gambar adalah nilai sebelum dipotong biaya transfer,
sementara acuan memakai nilai setelahnya. Ini perlu diperiksa manual bila angka
nominal dipakai untuk rekonsiliasi.

## Cakupan pengukuran

Pengukuran dilakukan pada **65 pasangan gambar-transaksi**, bukan 118 gambar.

| Cakupan | Bisa diukur |
|---|---|
| 65 baris dengan acuan | kelengkapan **dan** kecocokan |
| 53 gambar sisanya | kelengkapan saja, tanpa acuan |

Alasannya sama dengan SC-01: hanya 65 dari 118 foto yang bisa dipasangkan 1:1 ke
baris Cash Report lewat tanggal dan nominal. Untuk 53 gambar sisanya tidak ada
nilai pembanding, sehingga "terbaca benar" tidak bisa dinilai.

**Konsekuensinya:** angka 72,5% dan 95,2% berlaku untuk 65 baris, bukan klaim
atas seluruh 118 gambar seperti bunyi target BRD. Untuk memenuhi target apa
adanya, 53 gambar sisanya perlu dilengkapi acuan lebih dulu.

## Cara mengukur

```bash
python3 tests/sc_runner.py --download      # sekali saja
python3 tests/sc_runner.py --sc02          # ukur SC-02
python3 tests/sc_runner.py --all           # SC-01 dan SC-02 sekaligus
python3 tests/sc_runner.py --metrics-only --sc02   # hitung ulang, tanpa biaya
```

Panduan lengkap ada di [`sc-cara-menjalankan.md`](sc-cara-menjalankan.md).

## Aturan penilaian

Kelengkapan tidak diukur dengan "field kosong atau tidak", karena `main.extract`
mengisi nilai bawaan ketika model gagal membaca:

```python
"tanggal": data.get("tanggal") or datetime.now()...   # -> hari ini
"arah": arah if arah in (...) else "keluar"           # -> keluar
# bank kosong -> CR_DEFAULT_BANK
```

Penilaian memakai tiga sumber, berurutan dari yang paling dapat dipercaya:

1. `catatan` — `main.py` menulis "nominal tidak terbaca — isi manual" dan
   sejenisnya. Sinyal paling langsung.
2. `mode` — `mock` berarti model tidak dipanggil atau gagal total.
3. acuan — bila tersedia, nilai dibandingkan langsung.

Tanpa aturan ini, hasil akan tampak mendekati 100% padahal model tidak membaca
apa pun.

## Batasan

- Diukur pada 65 baris, bukan 118 gambar seperti bunyi target.
- Field `arah` tidak punya acuan di dataset, jadi hanya keterbacaan yang dinilai.
- Kolom `bank` di `sc01_pairs.csv` hanya terisi di 62 dari 65 baris.
- Angka berasal dari satu run. Model bersifat probabilistik, jadi satu run tidak
  cukup untuk klaim yang kuat; jalankan `--repeat 3` untuk melihat sebaran.
- Kategori diukur di SC-01 dan tidak boleh dipakai dua kali sebagai bukti
  kegagalan yang berbeda.
