# Kategori Transaksi

Daftar kategori tunggal untuk seluruh repo. Modul: `cash_report/categories.py`.

## Sumber nama

| Sumber | Dipakai untuk |
|---|---|
| `SOP Keuangan/Draft SOP Pencatatan Uang Keluar.pdf` | 10 kategori pengeluaran (tabel eksplisit) |
| Dropdown kolom `KATEGORI` pada Cash Report perusahaan | pemasukan, perpindahan dana, neraca |

SOP hanya mengatur uang keluar. Tidak ada dokumen perusahaan yang mengatur
kategori pemasukan, jadi tiga kategori `Pendapatan Usaha (...)` diambil dari
dropdown file Excel.

## Daftar final (23)

### Pemasukan (4)

| Kategori |
|---|
| `Pendapatan Usaha (Penjualan Produk)` |
| `Pendapatan Usaha (Penjualan Lainnya)` |
| `Pendapatan Usaha (Workshop)` |
| `Pendapatan Lain` |

### Perpindahan dana (1)

| Kategori | Catatan |
|---|---|
| `Transfer Antar Bank` | Dikecualikan dari RECAP dan laba rugi, tetap dihitung di saldo kantong |

### Neraca (3)

| Kategori |
|---|
| `Persediaan` |
| `Aset Tetap` |
| `Utang/Piutang` |

### Pengeluaran — dari SOP Pencatatan Uang Keluar (10)

| Kategori | Pemicu di SOP |
|---|---|
| `Bahan Baku` | pembelian bahan produksi |
| `Biaya-Gaji Karyawan` | pembayaran gaji |
| `Biaya-Konsumsi` | pembelian konsumsi |
| `Biaya-Perlengkapan Kantor dan Administrasi` | pembelian ATK |
| `Biaya-Transportasi` | biaya perjalanan dan kendaraan kantor |
| `Biaya-Ongkir` | pembayaran jasa pengiriman |
| `Biaya-Perbaikan Bangunan` | perbaikan fasilitas/bangunan |
| `Biaya-Operasional` | listrik, air, internet, kebersihan |
| `Biaya-Pembelian Aset` | pembelian peralatan/aset |
| `Biaya-Sosial` | bantuan/kegiatan sosial |

### Pengeluaran — tambahan dari dropdown (4)

| Kategori |
|---|
| `Biaya-Pajak` |
| `Biaya-Bunga Bank` |
| `Biaya-Administrasi Flip dan Bank` |
| `Beban Lain` |

### Penanda, bukan kategori akuntansi (1)

| Kategori | Catatan |
|---|---|
| `Perlu Ditinjau` | Diisi kode saat model tidak yakin. **Tidak ditawarkan ke model** |

## Yang sengaja tidak dimasukkan

Kategori berikut ada di file perusahaan tetapi ditolak, dengan alasan:

| Kategori | Alasan |
|---|---|
| `Saldo Awal` | Baris pembuka, bukan transaksi |
| `Beban Operasional-Gaji Karyawan` | Duplikat `Biaya-Gaji Karyawan` (skema berbeda) |
| `Beban Operasional - Perlengkapan Kantor dan Administrasi` | Duplikat `Biaya-Perlengkapan Kantor dan Administrasi` |
| `Beban Operasional - Transportasi` | Duplikat `Biaya-Transportasi` |
| `Beban Operasional-Konsumsi` | Duplikat `Biaya-Konsumsi` |
| `Beban Operasional-Listrik dan Internet` | Tercakup `Biaya-Operasional` |
| `Beban Operasional-R&D` | Tercakup `Biaya-Operasional` |
| `Beban Operasional-Pelatihan` | Tercakup `Biaya-Operasional` |
| `Marketing` | Tercakup `Biaya-Operasional` |
| `Royalti BRIN` | 0 pemakaian |
| `Profit Share Bangunan` | 0 pemakaian |
| `Bagi Hasil` | 0 pemakaian |
| `Pajak` | Duplikat `Biaya-Pajak` |
| `Biaya Sosial` | Duplikat `Biaya-Sosial` (kurang tanda hubung) |
| `Modal dan Prive` | Hanya ada di Diagram Alir, tidak di dropdown |

Kategori yang ditolak tetap bisa dikenali lewat `ALIAS` sehingga tidak hilang
tanpa jejak, kecuali empat yang memang tidak punya padanan:
`Bagi Hasil`, `Marketing`, `Profit Share Bangunan`, `Royalti BRIN`.
Keempatnya akan menjadi `Perlu Ditinjau` bila muncul.

## Pengelompokan bukan kolom baru

Lima kelompok di `categories.py` adalah **struktur kode**, bukan kolom di
ledger. Sheet `TRANSAKSI` tetap 11 kolom dan hanya menyimpan **satu** nilai
kategori per baris:

| Kolom | Isi |
|---|---|
| E `Kategori` | satu nama dari daftar final |

Kelompok itu dipakai untuk menentukan **di mana sebuah kategori ditampung**:

| Kelompok | Ditampung di | Masuk laba rugi |
|---|---|---|
| `PENDAPATAN` | SETUP kolom `KATEGORI PENDAPATAN` | ya, sebagai pendapatan |
| `PERPINDAHAN` | SETUP kolom `KATEGORI PENDAPATAN` | **tidak**, dikecualikan SUMIFS |
| `NERACA` | SETUP kolom `KATEGORI NERACA` | tidak |
| `PENGELUARAN_SOP` | SETUP kolom `KATEGORI PENGELUARAN` | ya, sebagai beban |
| `PENGELUARAN_TAMBAHAN` | SETUP kolom `KATEGORI PENGELUARAN` | ya, sebagai beban |

Sheet `SETUP` memakai **empat kolom**: `KANTONG`, `KATEGORI PENDAPATAN`,
`KATEGORI NERACA`, `KATEGORI PENGELUARAN`. Kolom neraca dipisah karena
`Persediaan`, `Aset Tetap`, dan `Utang/Piutang` bukan beban, sehingga tidak
boleh muncul di EXPENSE DETAIL maupun INCOME STATEMENT.

Alasan `PERPINDAHAN` ikut kolom pendapatan: `Transfer Antar Bank` perlu muncul
di dropdown kolom kategori saat admin mengisi manual, tetapi SUMIFS di RECAP,
YEARLY, EXPENSE DETAIL, dan INCOME STATEMENT semuanya mengecualikannya dengan
`TRANSAKSI!E:E,"<>Transfer Antar Bank"`. Jadi ia tampil sebagai pilihan tanpa
ikut terhitung sebagai pendapatan.

## Cara pakai

```python
from cash_report import categories as C

C.PROMPT_KATEGORI        # teks siap tempel untuk prompt (22 kategori)
C.KATEGORI               # 23, termasuk penanda
C.KATEGORI_UNTUK_MODEL   # 22, tanpa penanda
C.normalize(nilai)       # nama final, atau 'Perlu Ditinjau'
C.valid(nilai)           # True bila kategori sungguhan
```

`normalize()` tidak pernah mengembalikan `None`. Baris tanpa kategori tetap
tercatat, hanya ditandai supaya bisa diperiksa manusia.

## Alias yang ditangani

| Varian | Menjadi |
|---|---|
| `Beban Operasional-*` (7 varian) | `Biaya-*` sesuai padanan SOP |
| `Biaya-Perlengkapan Kantor dan Aministrasi` | `Biaya-Perlengkapan Kantor dan Administrasi` |
| `Biaya-Transporrtasi` | `Biaya-Transportasi` |
| `Biaya Sosial` | `Biaya-Sosial` |
| `Pajak` | `Biaya-Pajak` |
| `Bunga`, `Bunga Bank` | `Biaya-Bunga Bank` |
| `Administrasi Bank`, `Admin Flip`, `Admin Bank` | `Biaya-Administrasi Flip dan Bank` |
| `Penjualan`, `Penjualan Produk` | `Pendapatan Usaha (Penjualan Produk)` |
| `Lainnya`, `Lain-lain`, `Tidak diketahui`, kosong | `Perlu Ditinjau` |

## Peringatan saat mengubah daftar

1. **Jangan ubah string kategori** tanpa memperbarui template. SUMIFS di
   RECAP, EXPENSE DETAIL, dan INCOME STATEMENT mencocokkan string secara persis.
2. `build_template.py` memakai `EXP_ROW` yang diturunkan dari urutan
   `KAT_EXPENSE`. Baris 231 mengambil `EXP_ROW["Pajak"]` dan `EXP_ROW["Bunga"]`;
   kalau nama berubah, kunci itu harus ikut berubah.
3. Setelah mengubah daftar, jalankan `cash_report/verify_template.py` untuk
   memastikan 17 pemeriksaan masih lulus.
4. Template Google Sheets yang sudah ada perlu dibangun ulang
   (`build_template.py`) karena isi sheet SETUP adalah nilai statis.
