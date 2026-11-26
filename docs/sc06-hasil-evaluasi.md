# Hasil evaluasi SC-06: kelengkapan field yang diekstrak dari gambar

Dokumen ini melaporkan hasil pengukuran kriteria keberhasilan **SC-06** pada bot
pencatatan transaksi PT Lokal Komoditi Indonesia, Kelompok G3.

## Apa yang diukur

Ketika pengguna mengunggah gambar bukti transaksi, apakah **seluruh field wajib
benar-benar terbaca dari gambar itu**.

Yang **tidak** diukur di sini adalah kebenaran isinya. Nominal 20.000 yang
terbaca 50.000 tetap dihitung **terisi**; kecocokan nilai adalah urusan SC-01
dan SC-02. Kriteria ini hanya bertanya: field-nya ada atau tidak.

## Target

**Tidak ada field wajib yang hilang.** Dikutip dari tabel Success Criteria pada
BRD bagian 6.

## Angka yang dinilai

| Ukuran | Hasil | Target | Status |
|---|---|---|---|
| **Gambar lengkap seluruh field** | **37 dari 65 (56,9%)** | tidak ada yang hilang | **belum tercapai** |
| Gambar berhasil dipanggil | 65 dari 65 | — | — |
| Gambar gagal dipanggil | 0 | — | — |

**Yang dibandingkan dengan target adalah 37 dari 65 gambar**, bukan rata-rata
kelengkapan per field. Alasannya: BRD menyebut "tidak ada field wajib yang
hilang", dan satu gambar yang kehilangan satu field sudah berarti target belum
tercapai. Rata-rata per field akan menyembunyikan gambar yang bermasalah.

## Rincian per field

| Field | Terisi | Wajib | Kelengkapan |
|---|---|---|---|
| `tanggal` | 65 | 65 | **100,0%** |
| `keterangan` | 65 | 65 | **100,0%** |
| `nominal` | 65 | 65 | **100,0%** |
| `arah` | 65 | 65 | **100,0%** |
| `kategori` | 65 | 65 | **100,0%** |
| `bank` | 37 | 65 | **56,9%** |
| `kantong_tujuan` | 19 | 20 | 95,0% |

Enam dari tujuh field terbaca sempurna. **Seluruh kegagalan berasal dari satu
field: `bank`.**

## Penyebab kegagalan

### `bank` tidak terbaca pada 28 gambar

Model tidak menyebut kantong asal dana sama sekali pada 28 dari 65 gambar. Prompt
produksi untuk field ini berbunyi:

```
"bank":"kantong asal dana — salah satu dari: BRI, BNI, Jago, TUNAI;
 kosong bila tidak terbaca"
```

Kalimat "kosong bila tidak terbaca" memberi model izin mengosongkan field, dan
model memakai izin itu. Ini bukan regresi: prompt tersebut **byte-identik**
sebelum dan sesudah merge `main`, dan pengukuran SC-02 pada dataset yang sama
juga menemukan angka yang sama (56,9%).

### `kantong_tujuan` tidak terbaca pada 1 gambar

Satu gambar berarah `transfer` tetapi tidak menyebut kantong tujuan. Field ini
hanya wajib pada transaksi transfer, jadi penyebutnya 20, bukan 65. Pada 45
gambar lain field ini memang tidak wajib dan tidak dihitung.

## Kenapa diukur dari balasan model, bukan dari `main.extract()`

Ini bagian terpenting dokumen ini, karena mengubah cara pengukuran sebelumnya.

`main.extract()` **tidak pernah** mengembalikan field kosong. Setiap kegagalan
ditutupi nilai bawaan:

| Field kosong | Diisi produksi dengan |
|---|---|
| `tanggal` | `datetime.now()` |
| `arah` | `"keluar"` |
| `keterangan` | nama berkas |
| `bank` | `CR_DEFAULT_BANK` (bawaan `TUNAI`) |
| `kategori` | `PERLU_DITINJAU` |

Kalau penilaian memakai hasil fungsi itu, **semua gambar akan selalu tampak
lengkap** dan kriteria ini tidak mengukur apa pun. Karena itu harness menyimpan
balasan mentah model, dan penilaian dilakukan pada balasan itu.

Pada pengukuran ini, **nol** field ditutupi nilai bawaan. Artinya untuk dataset
ini, hasil `extract` kebetulan sama dengan balasan mentah. Itu bukan alasan
untuk kembali memakai `extract`: nilainya bergantung pada data, dan pada dataset
lain kegagalannya akan tersembunyi.

## Aturan penilaian

Daftar field dibaca dari **prompt produksi** di `main.py`, bukan disalin di kode
test. Kalau produksi menambah field, daftar itu ikut berubah dan test yang
membandingkannya akan gagal. Itu memang tujuannya, karena field baru perlu
diputuskan wajib atau tidak.

Sebuah field dinilai terisi bila memenuhi cara produksi membacanya:

| Field | Dinilai terisi bila |
|---|---|
| `tanggal` | bisa diurai jadi tanggal |
| `nominal` | angka dan bukan nol |
| `arah` | salah satu dari masuk, keluar, transfer |
| `kategori` | dikenali daftar kategori, bukan `PERLU_DITINJAU` |
| `keterangan` | ada isinya |
| `bank` | ada isinya |
| `kantong_tujuan` | ada isinya, **hanya bila** `arah` = transfer |

`keterangan` sengaja tidak memakai `_gabung_keterangan` milik produksi, karena
fungsi itu mengganti keterangan kosong dengan nama berkas sehingga kegagalan
model jadi tidak terlihat.

## Cara menjalankan

```bash
python3 tests/_sc06_run.py            # panggil model sekali per gambar
python3 tests/_sc06_run.py --limit 5  # uji cepat
python3 tests/_sc06_run.py --restart  # hitung ulang dari nol
python3 tests/sc_runner.py --sc06     # rangkum sampel, gratis
```

Hasil mentah disimpan di `sc-out/sc06_samples.csv` (di-ignore, memuat data
transaksi). Penilaian diturunkan ulang dari berkas itu, sehingga mengubah aturan
penilaian **tidak** memanggil model lagi dan tidak menambah biaya.

Biaya pengukuran ini: 65 panggilan model, sekitar Rp1.400 dengan tarif SC-04.

## Batas pengukuran

- Yang diukur hanya **ada atau tidaknya** field. Nilai yang salah tetap dihitung
  terisi, sesuai lingkup yang diminta.
- `bank` gagal terbaca pada 28 gambar, tetapi pengukuran ini tidak menyimpulkan
  apakah kegagalan itu wajar. Pada banyak bukti transfer, rekening asal memang
  tidak tercetak. Yang bisa dinyatakan: **prompt memberi izin mengosongkan, dan
  model memakainya pada 43% gambar**.
- Perbaikan `bank` adalah pekerjaan produksi (mengubah prompt atau menambah
  sumber informasi kantong), bukan pekerjaan testing.
