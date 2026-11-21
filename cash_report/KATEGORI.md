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

## Daftar final (31)

### Saldo awal (1)

| Kategori | Catatan |
|---|---|
| `Saldo Awal` | Baris pembuka buku, dipakai 11 kali Jan-Jul 2026. Dikenali kode, **tidak ditawarkan ke model** karena bukan transaksi yang difoto |

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

### Pengeluaran — tambahan dari dropdown (11)

| Kategori | Asal |
|---|---|
| `Biaya-Pajak` | dropdown, 18 sheet |
| `Biaya-Bunga Bank` | dropdown, 18 sheet |
| `Biaya-Administrasi Flip dan Bank` | dropdown, 18 sheet |
| `Biaya-Listrik dan Internet` | dropdown tab Salinan, rincian `Biaya-Operasional` |
| `Biaya-R&D` | dropdown tab Salinan, dipakai 2 kali di BRI Januari |
| `Biaya-Pelatihan` | dropdown tab Salinan, dipakai 2 kali di BRI Januari |
| `Beban Lain` | dropdown, 18 sheet |
| `Marketing` | dropdown tab Salinan, disebut di Diagram Alir |
| `Royalti BRIN` | dropdown tab Salinan, belum dipakai |
| `Profit Share Bangunan` | dropdown tab Salinan, belum dipakai |
| `Bagi Hasil` | dropdown tab Salinan, belum dipakai |

### Kategori dropdown yang belum pernah dipakai (4)

Tersedia di dropdown tab `Salinan` tetapi belum ada barisnya di data
Jan-Jul 2026. Tetap dimasukkan karena dropdown adalah kontrak dengan admin:
bulan mendatang bisa saja memakainya, dan menghilangkannya membuat admin tidak
bisa memilih kategori yang tersedia di file perusahaannya.

| Kategori | Dasar |
|---|---|
| `Marketing` | disebut eksplisit di Diagram Alir sebagai bagian beban operasional |
| `Royalti BRIN` | hanya ada di dropdown tab Salinan, tidak disebut di SOP |
| `Profit Share Bangunan` | idem |
| `Bagi Hasil` | idem |

### Penanda, bukan kategori akuntansi (1)

| Kategori | Catatan |
|---|---|
| `Perlu Ditinjau` | Diisi kode saat model tidak yakin. **Tidak ditawarkan ke model** |

## Cakupan terhadap 37 kategori dropdown

Ada 37 nilai unik di seluruh dropdown kolom `D` dari 3 file xlsx (22 sheet).
Nasib setiap nilai:

| Nasib | Jumlah | Keterangan |
|---|---|---|
| Ada langsung di daftar final | 27 | nama sama persis |
| Dikenali lewat alias | 10 | ejaan/skema berbeda, dipetakan ke nama baku |
| **Tidak ada di repo** | **0** | semua tercakup |

Seluruh 37 nilai dropdown dikenali. Tidak ada yang jatuh ke `Perlu Ditinjau`.

### Yang digabung atau diganti nama (10 alias)

| Varian | Menjadi | Alasan |
|---|---|---|
| `Beban Operasional-Gaji Karyawan` | `Biaya-Gaji Karyawan` | skema `Beban Operasional-*` vs `Biaya-*` |
| `Beban Operasional-Konsumsi` | `Biaya-Konsumsi` | idem |
| `Beban Operasional - Transportasi` | `Biaya-Transportasi` | idem |
| `Beban Operasional - Perlengkapan Kantor dan Administrasi` | `Biaya-Perlengkapan Kantor dan Administrasi` | idem |
| `Beban Operasional-Listrik dan Internet` | `Biaya-Listrik dan Internet` | idem |
| `Beban Operasional-R&D` | `Biaya-R&D` | idem |
| `Beban Operasional-Pelatihan` | `Biaya-Pelatihan` | idem |
| `Biaya-Perlengkapan Kantor dan Aministrasi` | `Biaya-Perlengkapan Kantor dan Administrasi` | typo asli, kurang huruf `d` |
| `Biaya Sosial` | `Biaya-Sosial` | kurang tanda hubung |
| `Pajak` | `Biaya-Pajak` | nama ringkas di tab Salinan |

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
| `SALDO_AWAL` | SETUP kolom `KATEGORI NERACA` | tidak |
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

C.PROMPT_KATEGORI        # teks siap tempel untuk prompt (29 kategori)
C.KATEGORI               # 31, termasuk Saldo Awal dan penanda
C.KATEGORI_UNTUK_MODEL   # 29, tanpa Saldo Awal dan tanpa penanda
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
