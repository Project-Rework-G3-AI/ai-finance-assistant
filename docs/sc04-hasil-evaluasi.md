# Hasil evaluasi SC-04: biaya per gambar

Dokumen ini melaporkan hasil pengukuran kriteria keberhasilan SC-04 pada bot
pencatatan transaksi PT Lokal Komoditi Indonesia, Kelompok G3.

## Apa yang diukur

Biaya satu gambar, dihitung dari token yang benar-benar terpakai:

```
biaya = (token prompt x tarif prompt) + (token completion x tarif completion)
        lalu dikonversi ke rupiah dengan kurs
```

Bukan waktu, bukan mutu isi. Kriteria ini mengukur **uang**.

## Target

**Di bawah Rp50 per gambar.**

## Hasil

Diukur pada **65 gambar**, satu run, 25 November 2026.

| Ukuran | Nilai |
|---|---|
| **Rata-rata biaya per gambar** | **Rp22,10** |
| Median | Rp14,66 |
| Persentil 90 | Rp44,65 |
| Termurah | Rp5,31 |
| Termahal | Rp72,55 |
| Di atas Rp50 | **4 dari 65 gambar** |

**Status: TERCAPAI.** Rata-rata Rp22,10, di bawah target Rp50.

Angka ini sudah dihitung ulang secara terpisah dari CSV mentah dan hasilnya
identik, jadi bukan kesalahan penjumlahan.

### Yang perlu dibaca dari tabel itu

Rata-rata lulus, tetapi **4 dari 65 gambar melewati Rp50**. Ini bukan kegagalan
kriteria, karena BRD menyebut target pada rata-rata, bukan per gambar. Tetapi
melaporkan "TERCAPAI" tanpa menyebut empat gambar itu akan menyesatkan.

Empat gambar termahal:

| Gambar | Biaya | Token prompt | Token completion |
|---|---|---|---|
| `photo_2026-01-09_21-02-41.jpg` | Rp72,55 | 984 | 6.388 |
| `photo_2026-01-09_15-52-34.jpg` | Rp65,54 | 1.046 | 5.731 |
| `photo_2026-01-15_17-38-46.jpg` | Rp64,84 | 984 | 5.683 |
| `photo_2026-01-20_09-39-28.jpg` | Rp53,14 | 958 | 4.620 |

Polanya jelas: **token prompt hampir tetap (sekitar 950), yang melonjak adalah
token completion.** Prompt-nya sama panjang untuk semua gambar, karena isinya
instruksi tetap ditambah satu gambar. Yang bervariasi adalah panjang jawaban
model. Empat gambar di atas memakai 4.600 sampai 6.400 token untuk menjawab,
sementara median hanya 1.079.

Artinya pembengkakan biaya berasal dari model yang menulis jawaban panjang,
bukan dari gambar yang lebih besar. Ini sejalan dengan temuan SC-03 bahwa
`extract` mendominasi waktu: gambar yang lambat kemungkinan besar juga gambar
yang jawabannya panjang.

## Tarif yang dipakai

| Komponen | Tarif |
|---|---|
| Model | `deepseek/deepseek-v4.1-flash-1017` |
| Prompt | $0,00000015 / token |
| Completion | $0,0000006 / token |
| Kurs | Rp18.227 per USD |
| Sumber tarif | katalog OpenRouter saat pengukuran |

Model ini dibaca langsung dari `.env` proyek di host, bukan ditebak. Varian
`-1017` dipakai karena hanya varian itu yang menerima gambar; varian tanpa
akhiran hanya teks.

## Cara menyesuaikan tarif

Tarif berubah dan kurs berubah, jadi tidak ada angka tarif yang dipatok di dalam
logika. Yang mengubah hasil ada di satu tempat, di bagian atas
`tests/sc04_cost.py`:

```python
PRICE_PROMPT_USD = 0.00000015
PRICE_COMPLETION_USD = 0.0000006
```

Ubah dua angka itu, seluruh laporan ikut berubah. Ini bukan sekadar teori:
mengubahnya menjadi dua kali lipat mengubah rata-rata dari Rp14,82 menjadi
Rp29,64 pada data yang sama.

Selain menyunting kode, bisa juga ditimpa untuk satu kali jalan tanpa mengubah
berkas:

| Cara | Contoh |
|---|---|
| Argumen CLI | `--price-prompt 0.0000003 --price-completion 0.0000012` |
| Variabel lingkungan | `SC04_PRICE_PROMPT_USD=... SC04_PRICE_COMPLETION_USD=...` |
| Kurs | `--usd-idr 18227` atau `SC04_USD_IDR=18227` |
| Target | `--target-idr 40` atau `SC04_TARGET_IDR=40` |

Urutan siapa yang menang: **CLI, lalu env, lalu variabel di kode, lalu katalog
penyedia.** Tarif di kode yang masih nol dianggap belum diisi, sehingga katalog
yang dipakai. Tidak ada tarif yang ditebak.

### Kenapa biaya tidak disimpan

Berkas `sc04_samples.csv` hanya menyimpan **token**, bukan biaya:

```
file,ok,error,prompt_tokens,completion_tokens
```

Biaya selalu diturunkan ulang dari token dikali tarif dikali kurs yang berlaku
saat laporan dibuat. Kalau biaya ikut disimpan, mengubah tarif tidak akan
berefek pada angka yang sudah ada, dan penyesuaian tarif jadi sia-sia. Ini
dikunci oleh test.

## Batas pengukuran

1. **65 gambar, bukan 118.** Hanya 65 foto yang punya acuan di `pairs.csv`.
2. **Satu run.** Biaya per gambar bergantung pada panjang jawaban model, dan
   panjang jawaban bervariasi antar-run. Angka ini satu kali pengukuran, bukan
   rentang.
3. **Token dibaca dari `usage` penyedia**, bukan ditaksir dari panjang teks.
   Taksiran akan menghasilkan angka yang terlihat masuk akal tetapi tidak benar.
4. **Kurs satu titik waktu.** Rp18.227 per USD pada 25 November 2026. Kalau kurs
   bergerak, angkanya bergerak.
5. **Tidak termasuk biaya lain.** Hanya panggilan model. Penyimpanan Sheets,
   Drive, dan hosting tidak dihitung.

## Hubungan dengan SC-03

SC-03 menemukan waktu terbesar habis di `extract`. SC-04 menemukan biaya
terbesar juga di `extract`, khususnya di token completion. Keduanya menunjuk
sumber yang sama: **panjang jawaban model.**

Konsekuensi praktisnya: memperpendek jawaban model akan menurunkan biaya **dan**
waktu sekaligus. Ini satu perbaikan untuk dua kriteria yang gagal.

## Cara menjalankan ulang

```bash
# Ukur semua gambar (butuh kredensial dan kurs)
python3 tests/_sc04_run.py --usd-idr 18227

# Coba cepat pada 5 gambar
python3 tests/_sc04_run.py --limit 5 --usd-idr 18227

# Hitung ulang laporan tanpa memanggil model
python3 tests/sc_runner.py --sc04 --metrics-only
```

## Berkas

| Berkas | Isi |
|---|---|
| `tests/sc04_cost.py` | rumus biaya, tarif yang bisa disunting, penyusunan laporan |
| `tests/test_sc04_cost.py` | 35 test yang mengunci aturan perhitungan |
| `tests/_sc04_run.py` | pengukur: memanggil penyedia, membaca `usage` |
| `sc-out/sc04_samples.csv` | token per gambar (tanpa biaya) |
| `sc-out/sc04_report.txt` | laporan teks |
| `sc-out/sc04_metrics.json` | ringkasan dalam bentuk JSON |
