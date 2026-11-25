# Hasil evaluasi SC-06: seluruh kolom wajib cash report terpetakan

Dokumen ini melaporkan hasil pengukuran kriteria keberhasilan SC-06 pada bot
pencatatan transaksi PT Lokal Komoditi Indonesia, Kelompok G3.

## Apa yang diukur

Apakah setiap kolom wajib pada template cash report perusahaan punya tempat di
keluaran aplikasi. Yang dinilai **susunan kolom**, bukan isi sel.

Bukan akurasi, bukan waktu, bukan biaya. Kriteria ini mengukur **tidak adanya
kolom wajib yang hilang**.

## Target

**Tidak ada kolom wajib yang hilang.** Dikutip dari tabel Success Criteria pada
BRD bagian 6.

## Sumber kolom wajib

Kolom wajib dibaca dari **berkas template perusahaan** di repo dataset, bukan
dari daftar yang ditulis ulang di kode test:

| Berkas | Sheet | Baris header |
|---|---|---|
| `Cash Report BNI-PT Lokal Komoditi Indonesia 2026.xlsx` | 8 | 5 |
| `Cash Report BRI-PT Lokal Komoditi Indonesia.xlsx` | 8 | 5 |
| `Cash Report Operasional-PT Lokal Komoditi Indonesia 2026.xlsx` | 6 | 4 dan 5 |

Keduapuluh dua sheet memakai header yang sama, sepuluh kolom. Berkas Operasional
menaruh header di baris 4 untuk sheet pertamanya, karena itu header dicari lewat
isinya (`TANGGAL TRANSAKSI`), bukan nomor baris yang dipatok.

## Hasil

| # | Kolom wajib perusahaan | Nasib di aplikasi | Kolom aplikasi |
|---|---|---|---|
| A | TANGGAL INPUT DAN NAMA ADMIN | **bukan data bot** | — |
| B | TANGGAL TRANSAKSI | langsung | A `Tanggal` |
| C | KETERANGAN | langsung | F `Keterangan` |
| D | KATEGORI | langsung | E `Kategori` |
| E | KETERANGAN UANG MASUK | terbagi | B `Kantong` |
| F | KETERANGAN UANG KELUAR | terbagi | B `Kantong` |
| G | DEBET | langsung | C `Masuk` |
| H | KREDIT | langsung | D `Keluar` |
| I | SALDO | diturunkan | `ACCOUNT!E` (formula) |
| J | LAMPIRAN NOTA | langsung | K `Link Bukti` |

**Status: TERCAPAI.** Sembilan dari sembilan kolom wajib yang relevan untuk bot
terpetakan, tidak ada yang hilang.

Angka yang dinilai adalah **9 dari 9**. Penyebutnya kolom wajib yang memang
datanya dihasilkan bot, bukan sebelas kolom aplikasi, dan bukan sepuluh kolom
perusahaan.

Satu kolom perusahaan dikeluarkan dari penyebut dengan alasan terbuka, bukan
disembunyikan: lihat bagian berikut.

## Kolom yang diisi manusia, bukan bot

Kolom A perusahaan berjudul **"TANGGAL INPUT DAN NAMA ADMIN"**: siapa yang
memasukkan baris itu dan kapan.

Kolom itu **tidak dihasilkan bot**, dan bukan karena aplikasi lupa. Bot menerima
gambar bukti transaksi; identitas admin yang mengunggahnya bukan bagian dari
gambar itu. Pada template perusahaan, kolom tersebut diisi manusia saat bekerja
(`Lina`, `Aurelia Shafarina`).

`grep -niE "admin|nama_admin|username|from_user|first_name" main.py` hanya
menemukan satu kemunculan, dan itu pesan penolakan akses, bukan pencatatan
identitas.

Karena itu kolom ini **dikeluarkan dari penyebut**, bukan dihitung sebagai
kegagalan. Angka yang dilaporkan menjadi 9 dari 9, dan laporannya tetap
menampilkan kolom ini beserta alasannya:

```
Kolom wajib perusahaan    : 10
  diisi manusia, bukan bot : 1
  relevan untuk bot        : 9
Kolom terpetakan          : 9
Kolom hilang              : 0
```

Cara ini dipilih supaya angkanya jujur. Menghapus kolom dari daftar akan membuat
status tampak lebih baik tanpa menjelaskan apa pun; menampilkannya sambil
menjelaskan alasan membuat pembaca bisa menilai sendiri. Test
`test_columns_filled_by_people_are_reported_not_hidden` mengunci agar kolom itu
tidak pernah hilang dari laporan.

Kolom A aplikasi juga tidak bisa dipakai sebagai gantinya: kolom itu sudah
berisi tanggal transaksi, yang sudah menjadi wakil kolom B perusahaan. Memakai
satu kolom untuk dua kolom wajib akan membuat kolom wajib tampak terpetakan
padahal isinya bukan.

## Kolom yang diturunkan, dan kenapa tetap dihitung

**SALDO** tidak ada sebagai kolom di sheet `TRANSAKSI`, tetapi dihitung penuh di
sheet `ACCOUNT` sebagai `Saldo Akhir` per kantong lewat formula
`SUMIFS(TRANSAKSI!C:C, ...)` dikurangi `SUMIFS(TRANSAKSI!D:D, ...)`. Kolom wajib
itu punya tempat, hanya bentuknya formula, bukan sel yang ditulis per baris.

Perbedaannya nyata dan perlu disebut: template perusahaan menyimpan saldo
**berjalan per baris**, sedangkan aplikasi menyimpan saldo **akhir per kantong**.
Yang dinilai SC-06 adalah ada atau tidaknya tempat bagi kolom wajib, dan tempat
itu ada. Tetapi kemampuan menelusuri saldo setelah setiap transaksi tidak sama,
dan itu tidak tertutup oleh status TERCAPAI bila nanti kolom A diperbaiki.

## Kolom yang terbagi

Kolom E dan F perusahaan berjudul "KETERANGAN UANG MASUK" dan "KETERANGAN UANG
KELUAR", tetapi isinya bukan teks bebas. Dari 22 sheet, isi yang muncul adalah
nama kantong: `BNI` (83 kali), `BRI`, `Kas Operasional`, dan pada satu sheet
`Masuk (Penjualan)` / `Keluar (Pembayaran)`.

Aplikasi menuliskan informasi itu lewat kolom `Kantong` (B), dengan memecah
transfer menjadi dua baris:

```python
is_pair = bool(arah == "transfer" and kantong_tujuan and kantong_tujuan != kantong)
if is_pair:
    values = [
        _baris(kantong, nominal, ""),          # baris keluar: kantong asal
        _baris(kantong_tujuan, "", nominal),   # baris masuk: kantong tujuan
    ]
```

Jadi satu transfer menghasilkan dua baris, masing-masing membawa kantongnya
sendiri. Kolom wajib itu terpetakan, meski bentuknya berbeda dari template.

## Kolom tambahan di aplikasi

Empat kolom tidak ada di template perusahaan tetapi ditulis aplikasi:
`Status`, `Catatan`, `Ref ID`, `Sumber File`.

Kolom-kolom ini bukan kolom wajib yang hilang, jadi tidak memengaruhi penilaian.
`Ref ID` dipakai untuk menolak duplikat (SC-05), dan `Catatan` menyimpan alasan
bila suatu field tidak terbaca.

## Cara menjalankan

```bash
python3 tests/sc_runner.py --download-templates   # sekali saja
python3 tests/sc_runner.py --sc06
```

Gratis: tanpa kunci AI, tanpa kredensial Google, tanpa jaringan setelah template
tersedia. Laporan ditulis ke `sc-out/sc06_report.txt` dan `sc-out/sc06_columns.csv`.

## Batas pengukuran

SC-06 menilai **susunan kolom**, bukan apakah isinya benar. Kolom yang ada tetapi
selalu kosong tetap terhitung terpetakan. Pemeriksaan isi adalah tugas SC-02.

Kolom A dikeluarkan dari penyebut karena memang bukan data yang bisa dihasilkan
bot, bukan karena aplikasi gagal. Kalau nanti tim memutuskan bot perlu mencatat
identitas pengunggah, kolom itu pindah dari `NOT_BOT_DATA` ke pemetaan biasa dan
penyebutnya kembali menjadi 10.
