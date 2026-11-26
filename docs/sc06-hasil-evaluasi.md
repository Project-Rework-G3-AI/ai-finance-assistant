# Hasil evaluasi SC-06: hasil pencatatan memetakan seluruh kolom wajib cash report

Dokumen ini melaporkan hasil pengukuran kriteria keberhasilan **SC-06** pada bot
pencatatan transaksi PT Lokal Komoditi Indonesia, Kelompok G3.

## Target

**Tidak ada kolom wajib yang hilang.** Dikutip dari tabel Success Criteria pada
BRD bagian 6.

## Cara memeriksa menurut BRD

BRD menuliskan caranya secara eksplisit:

> Membandingkan **susunan kolom** keluaran dengan kolom wajib pada template cash
> report perusahaan.

Kalimat itu menunjuk dua hal yang harus diperiksa, dan keduanya diukur:

1. **Susunan kolom** — setiap kolom wajib template perusahaan punya tempat di
   keluaran aplikasi.
2. **Hasil pencatatan** — setiap baris yang benar-benar ditulis punya kolom
   wajib terisi.

Bagian 1 saja tidak cukup: susunan kolom bisa lengkap sementara isinya kosong.
Bagian 2 saja juga tidak cukup: satu baris bisa lengkap sementara ada kolom
perusahaan yang tidak punya tempat sama sekali.

## Hasil

| Bagian | Hasil | Status |
|---|---|---|
| **1. Susunan kolom** | 9 dari 9 kolom relevan bot punya tempat, **0 hilang** | tercapai |
| **2. Hasil pencatatan** | **79 dari 79 baris** lengkap seluruh kolom wajib | tercapai |
| **Keseluruhan** | | **TERCAPAI** |

Angka yang dibandingkan dengan target adalah **79 dari 79 baris**. Enam puluh
lima gambar menghasilkan 79 baris karena 14 transfer dipecah menjadi dua baris
(keluar dari kantong asal, masuk ke kantong tujuan).

## Bagian 1: susunan kolom

Kolom wajib dibaca dari **tiga berkas template perusahaan** di repo dataset,
bukan dari daftar yang ditulis ulang di kode test:

| Berkas | Sheet | Baris header |
|---|---|---|
| `Cash Report BNI-PT Lokal Komoditi Indonesia 2026.xlsx` | 8 | 5 |
| `Cash Report BRI-PT Lokal Komoditi Indonesia.xlsx` | 8 | 5 |
| `Cash Report Operasional-PT Lokal Komoditi Indonesia 2026.xlsx` | 6 | 4 dan 5 |

Keduapuluh dua sheet memakai header yang sama, sepuluh kolom. Header dicari
lewat isinya (`TANGGAL TRANSAKSI`), bukan nomor baris, karena berkas Operasional
menaruhnya di baris 4.

Setiap kolom punya keputusan tertulis, bukan hasil tebakan pencocokan nama:

| # | Kolom perusahaan | Nasib | Kolom aplikasi |
|---|---|---|---|
| A | `TANGGAL INPUT DAN NAMA ADMIN` | bukan data bot | — |
| B | `TANGGAL TRANSAKSI` | langsung | A |
| C | `KETERANGAN` | langsung | F |
| D | `KATEGORI` | langsung | E |
| E | `KETERANGAN UANG MASUK` | terbagi | B |
| F | `KETERANGAN UANG KELUAR` | terbagi | B |
| G | `DEBET` | langsung | C |
| H | `KREDIT` | langsung | D |
| I | `SALDO` | diturunkan | `ACCOUNT!E` |
| J | `LAMPIRAN NOTA` | langsung | K |

`TANGGAL INPUT DAN NAMA ADMIN` diisi manusia di template: bot menerima gambar
bukti transaksi, bukan identitas admin yang mengunggahnya. Kolom itu tetap
ditampilkan beserta alasannya, tetapi dikeluarkan dari penyebut. Yang dinilai
adalah **9 dari 9** kolom yang relevan untuk bot.

`SALDO` tidak ditulis per baris: ia dihitung formula di sheet `ACCOUNT` (kolom
E, Saldo Akhir per kantong).

`KETERANGAN UANG MASUK` dan `KETERANGAN UANG KELUAR` di template berisi **nama
kantong**, bukan teks bebas (`BNI` 83 kali, `BRI`, `Kas Operasional`). Aplikasi
menuliskannya lewat kolom Kantong (B) dengan memecah transfer menjadi dua baris.

## Bagian 2: kelengkapan hasil pencatatan

Setiap baris yang ditulis diperiksa kolom wajibnya:

| Kelompok kolom | Aturan penilaian |
|---|---|
| `TANGGAL TRANSAKSI`, `KETERANGAN`, `KATEGORI` | wajib terisi |
| `DEBET` / `KREDIT` | **berpasangan** — satu baris hanya mengisi salah satunya |
| `KETERANGAN UANG MASUK` / `KELUAR` | berpasangan, sama seperti di atas |
| `SALDO` | dihitung formula, tidak dinilai per baris |
| `LAMPIRAN NOTA` | tidak diukur (lihat batas pengukuran) |

Menilai `DEBET` dan `KREDIT` sebagai dua kolom wajib terpisah adalah kesalahan
hitung: setiap baris akan dianggap kurang padahal memang hanya satu yang terisi.
Aturan berpasangan ini dikunci test.

Hasil: **79 baris ditulis, 79 lengkap, 0 kurang.**

## Yang tidak diukur di sini

**Kebenaran nilai.** Nominal 20.000 yang terbaca 50.000 tetap dihitung terisi.
Kecocokan nilai adalah SC-01 (kategori) dan SC-02 (kelengkapan field).

**Kebenaran kantong asal.** Ini penting dan perlu dinyatakan terbuka.

Produksi mengisi kolom Kantong dengan `CR_DEFAULT_BANK` (`TUNAI`) ketika model
gagal membaca kantong asal (`main.py:425`). Kolomnya jadi selalu terisi, jadi
bagian 2 tidak bisa mendeteksinya.

Pada dataset ini, **12 dari 65 gambar** adalah transfer yang kantong asalnya
tidak terbaca, sehingga tercatat "keluar dari TUNAI" padahal dananya bukan kas
tunai. Cacat itu dilaporkan terpisah di
[`bug-kantong-tunai.md`](bug-kantong-tunai.md), bukan dijadikan angka kriteria
ini, karena kalimat BRD untuk SC-06 memeriksa keberadaan kolom, bukan kebenaran
isinya.

**`LAMPIRAN NOTA`.** Isinya URL hasil unggah Drive. Harness SC-06 tidak
mengaktifkan Drive, jadi kolom itu dilaporkan "tidak diukur" dan dikeluarkan
dari penyebut, bukan dianggap gagal. Kalau dihitung sebagai gagal, yang
dilaporkan adalah kegagalan harness, bukan kegagalan aplikasi.

## Angka pendukung: kelengkapan field per gambar

Diukur terpisah, **bukan** angka SC-06. Berguna sebagai bukti pendukung untuk
menunjukkan field mana yang paling sering gagal dibaca model.

| Field | Terisi | Wajib | Kelengkapan |
|---|---|---|---|
| `tanggal` | 65 | 65 | 100,0% |
| `keterangan` | 65 | 65 | 100,0% |
| `nominal` | 65 | 65 | 100,0% |
| `arah` | 65 | 65 | 100,0% |
| `kategori` | 65 | 65 | 100,0% |
| `bank` | 37 | 65 | **56,9%** |
| `kantong_tujuan` | 19 | 20 | 95,0% |

37 dari 65 gambar lengkap seluruh field. Seluruh kekurangan berasal dari satu
field: `bank`. Angka ini **tidak** dipakai sebagai verdict SC-06, karena SC-06
mengukur pemetaan kolom, sedangkan kelengkapan field adalah lingkup SC-02.

## Cara menjalankan

```bash
python3 tests/sc_runner.py --download-templates  # sekali saja
python3 tests/_sc06_run.py                       # ambil balasan model (berbiaya)
python3 tests/sc_runner.py --sc06                # laporan, gratis
```

Bagian 1 hanya butuh berkas template. Bagian 2 butuh `sc06_samples.csv` yang
diisi `_sc06_run.py`; tanpa berkas itu, bagian 2 dilaporkan BELUM DIUKUR dan
verdict tidak hijau.

Biaya pengambilan sampel: 65 panggilan model, sekitar Rp1.400 dengan tarif SC-04.
Penilaian diturunkan ulang dari sampel, jadi mengubah aturan penilaian tidak
memanggil model lagi.

## Batas pengukuran

- Yang diukur hanya **keberadaan** kolom wajib, bukan kebenaran isinya.
- Kebenaran kantong asal tidak terdeteksi (lihat `bug-kantong-tunai.md`).
- `LAMPIRAN NOTA` tidak diukur karena butuh Drive aktif.
- Pengukuran bagian 2 memakai tiruan penulisan baris yang **dijaga test**
  membandingkannya dengan `main.write_cash_report`. Kalau produksi berubah,
  test itu gagal, sehingga angka ini tidak bisa diam-diam mengukur tiruan.
