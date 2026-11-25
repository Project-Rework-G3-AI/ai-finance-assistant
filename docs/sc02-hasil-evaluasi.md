# SC-02 — Hasil evaluasi kelengkapan field wajib

Dokumen ini mencatat hasil pengukuran kriteria keberhasilan **SC-02** pada BRD:
persentase field wajib yang **terbaca benar** dari gambar bukti transaksi.

**Target BRD:** minimal 90% field wajib terbaca benar pada 118 gambar uji
Januari 2026.

## Angka mana yang dibandingkan dengan target

Ini pertanyaan pertama yang wajar muncul, karena laporan memuat beberapa angka
sekaligus. Jawabannya:

| Angka | Nilai | Dipakai menilai target? |
|---|---|---|
| Kelengkapan rata-rata | 90,2% | **tidak** |
| Kecocokan rata-rata | **64,5%** | **ya** |
| Kecocokan tanpa kategori | 83,4% | tidak, hanya penjelas |

**Yang dibandingkan dengan target 90% adalah kecocokan rata-rata 64,5%.**

Alasannya: BRD menyebut "terbaca **benar**", bukan "terisi". Kelengkapan 90,2%
hanya berarti model membaca sesuatu di hampir semua field, termasuk saat
nilainya salah. Jadi angka itu tidak boleh dipakai menilai target.

Penyebut 64,5% adalah **4 field**, bukan 5. Field `arah` tidak punya acuan di
dataset, jadi tidak ikut dirata-rata. Rata-rata dihitung per field, bukan per
baris, supaya satu field yang selalu gagal tidak tertutup oleh field lain yang
selalu berhasil.

## Ringkasan

| Ukuran | Hasil | Target | Status |
|---|---|---|---|
| Kelengkapan (field terbaca) | **90,2%** | — | bukan penentu |
| **Kecocokan (terbaca benar)** | **64,5%** | 90% | **belum tercapai** |
| Kecocokan tanpa kategori | 83,4% | — | penjelas sebab |
| Baris dengan 5/5 field lengkap | **37 dari 65** | — | — |

## Rincian per field

| Field | Terbaca | Kelengkapan | Cocok | Akurasi | Nilai bawaan terpakai |
|---|---|---|---|---|---|
| Tanggal | 64/65 | 98,5% | 64 | **98,5%** | 0 |
| Nominal | 64/65 | 98,5% | 63 | **96,9%** | 0 |
| Kantong | 37/65 | 56,9% | 34 | **54,8%** | 27 |
| Arah | 64/65 | 98,5% | — | tidak dinilai | 0 |
| Kategori | 64/65 | 98,5% | 5 | **7,7%** | 0 |

Kolom "cocok" untuk kantong berpenyebut 62, bukan 65, karena hanya 62 baris di
`pairs.csv` yang punya acuan `bank`. Kolom "arah" tidak dinilai karena
dataset tidak menyediakan acuan arah.

Seluruh angka dihitung dari **64 baris bermode `vision`**. Satu baris jatuh ke
`mock` karena pemanggilan model gagal, dan baris itu dihitung sebagai tidak
terbaca, bukan dilewati.

## Riwayat pengukuran

Angka di dokumen ini **berbeda** dari pengukuran sebelumnya (72,5%), dan
perbedaannya bukan karena kode test berubah:

| Field | Sebelum merge | Sesudah merge | Selisih |
|---|---|---|---|
| Tanggal | 100,0% | 98,5% | −1,5 |
| Nominal | 98,5% | 96,9% | −1,6 |
| Kantong | 87,1% | 54,8% | **−32,3** |
| Kategori | 4,6% | 7,7% | +3,1 |
| **Rata-rata** | **72,5%** | **64,5%** | **−8,0** |

Penurunan terbesar ada di kantong: 27 dari 65 gambar tidak menyebut kantong sama
sekali, sehingga kode memakai nilai bawaan. Prompt produksi untuk field ini
tidak berubah antar-merge (`"bank":"kantong asal dana — salah satu dari: BRI,
BNI, Jago, TUNAI; kosong bila tidak terbaca"`), jadi ini bukan regresi prompt.

Satu hal yang perlu dicatat: `.env` pengukuran hanya memuat kunci model, tanpa
`CR_DEFAULT_BANK`. Nilai bawaannya `TUNAI`, dan 27 baris itu menyimpan kantong
kosong alih-alih `TUNAI` karena nilainya dibaca lewat jalur yang berbeda di
`main.py` (baris 425 memakai nilai bawaan, baris 787 tidak). Perbedaan itu tidak
mengubah angka terbaca, tetapi menjelaskan kenapa kolom kantong bisa kosong
meski ada nilai bawaan.

## Sebab kegagalan satu baris

Satu gambar, `photo_2026-01-15_20-40-42.jpg`, gagal total dan jatuh ke mock:

```
TypeError: expected string or bytes-like object, got 'NoneType'
```

Penyebabnya di `main.py`: balasan model dibaca `r.json()["choices"][0]["message"]["content"]`
lalu diberikan ke `re.search(r"\{.*\}", text, re.S)`. Ketika model membalas
`content: null`, `re.search` menerima `None` dan melempar `TypeError`. Ekstraksi
lalu jatuh ke `_mock_extract`, sehingga transaksi itu tidak pernah dibaca model.

Pemanggilan itu juga memakan **461 detik**, jauh di atas rata-rata 10 detik,
karena percobaan pertama menghabiskan waktu sebelum gagal.

## Temuan utama

### Kategori menyeret seluruh angka

Kalau keempat field beracuan dirata-ratakan, hasilnya 72,5% dan target tidak
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

**Cara melaporkan.** Status resmi memakai 72,5% (semua field beracuan), karena
BRD menyebut "field wajib" tanpa pengecualian. Angka 95,2% dilaporkan
berdampingan sebagai penjelas sebab, bukan sebagai pengganti status.

Kategori tetap dihitung di SC-02 karena ia field wajib. Tetapi kategori juga
diukur di SC-01, jadi menyebut 4,6% dua kali berisiko membuat satu akar masalah
tampak seperti dua kegagalan. Kalimat yang jujur: target SC-02 gagal, dan
penyebab utamanya adalah field kategori yang sudah punya kriteria sendiri.

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
python3 tests/sc_runner.py                 # semua kriteria sekaligus
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
- Kolom `bank` di `pairs.csv` hanya terisi di 62 dari 65 baris.
- Angka berasal dari satu run. Model bersifat probabilistik, jadi satu run tidak
  cukup untuk klaim yang kuat; jalankan `--repeat 3` untuk melihat sebaran.
- Kategori diukur di SC-01 dan tidak boleh dipakai dua kali sebagai bukti
  kegagalan yang berbeda.
