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

### Cara daftar ini diverifikasi

Daftar ini tidak disusun dari ingatan. `tests/test_categories_fidelity.py`
membaca langsung ketiga file Excel perusahaan dan memeriksa dua arah:

| Arah | Aturan |
|---|---|
| Dataset ke repo | setiap kategori di dropdown harus dikenali, langsung atau lewat alias |
| Repo ke dataset | setiap nama di `KATEGORI` harus ada **byte-identik** di file Excel, kecuali penanda internal |

Hal yang mudah terlewat dan sudah ditangani:

- **Satu sheet bisa punya beberapa blok dropdown** dengan daftar berbeda.
  `Cash Report Operasional` Januari dan Maret masing-masing punya dua blok
  (`D5:D25` dan `D26:D39`), dan isinya tidak sama.
- **Excel memecah daftar panjang** menjadi beberapa potongan string yang
  disambung `&`. Parser yang berhenti di potongan pertama akan kehilangan
  sebagian kategori.
- **Kolom D memuat sel header** bernama `KATEGORI` yang bukan kategori.

Angka acuan: **37 kategori unik** dari 22 sheet di 3 file. Semua terwakili di
`categories.py`; 31 berdiri sebagai nama final, 6 sisanya varian ejaan yang
sah dan dipetakan lewat `ALIAS`.

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
| `Beban Operasional-Listrik dan Internet` | dropdown tab Salinan, ejaan asli dipertahankan |
| `Beban Operasional-R&D` | dropdown tab Salinan, dipakai 2 kali di BRI Januari |
| `Beban Operasional-Pelatihan` | dropdown tab Salinan, dipakai 2 kali di BRI Januari |
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
| `Beban Operasional-RD` | `Beban Operasional-R&D` | varian tanpa `&`, salah ketik |
| `Biaya-Perlengkapan Kantor dan Aministrasi` | `Biaya-Perlengkapan Kantor dan Administrasi` | typo asli, kurang huruf `d` |
| `Biaya Sosial` | `Biaya-Sosial` | kurang tanda hubung |
| `Pajak` | `Biaya-Pajak` | nama ringkas di tab Salinan |

## Nama kategori memakai ejaan dataset

30 dari 31 nama di `categories.py` **persis sama** dengan string di file
perusahaan. Satu-satunya yang bukan berasal dari dataset adalah `Perlu
Ditinjau`, penanda internal yang tidak ditawarkan ke model.

Tiga kategori hanya ada dalam ejaan `Beban Operasional-*` di tab Salinan, tanpa
padanan `Biaya-*` di file mana pun:

| Nama di dataset | Dipakai |
|---|---|
| `Beban Operasional-Listrik dan Internet` | 0 baris |
| `Beban Operasional-R&D` | 2 baris (BRI Januari) |
| `Beban Operasional-Pelatihan` | 2 baris (BRI Januari) |

Ketiganya sengaja **tidak** dibakukan ke pola `Biaya-*` seperti tujuh kategori
lain. Membakukan nama yang tidak pernah ada di file perusahaan akan menghasilkan
string baru yang tidak dikenali siapa pun, dan membuat sistem tidak bisa
mencocokkan data lama.

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
| `PERPINDAHAN` | SETUP kolom `KATEGORI LAIN` | **tidak**, dikecualikan SUMIFS |
| `NERACA` | SETUP kolom `KATEGORI NERACA` | tidak |
| `PENGELUARAN_SOP` | SETUP kolom `KATEGORI PENGELUARAN` | ya, sebagai beban |
| `PENGELUARAN_TAMBAHAN` | SETUP kolom `KATEGORI PENGELUARAN` | ya, sebagai beban |
| penanda `Perlu Ditinjau` | SETUP kolom `KATEGORI LAIN` | tidak |

Sheet `SETUP` memakai **lima kolom**: `KANTONG`, `KATEGORI PENDAPATAN`,
`KATEGORI NERACA`, `KATEGORI PENGELUARAN`, `KATEGORI LAIN`. Kolom neraca
dipisah karena `Persediaan`, `Aset Tetap`, dan `Utang/Piutang` bukan beban,
sehingga tidak boleh muncul di EXPENSE DETAIL maupun INCOME STATEMENT.

**Setiap kategori menempati tepat satu kolom.** Sebelumnya `Transfer Antar
Bank` masuk kolom pendapatan sekaligus pengeluaran, sehingga admin melihatnya
dua kali di dropdown dengan makna berbeda. Sekarang ia hanya ada di
`KATEGORI LAIN`, bersama penanda `Perlu Ditinjau`.

`Transfer Antar Bank` tetap muncul sebagai pilihan, tetapi SUMIFS di RECAP,
YEARLY, EXPENSE DETAIL, dan INCOME STATEMENT semuanya mengecualikannya dengan
`TRANSAKSI!E:E,"<>Transfer Antar Bank"`, jadi tidak ikut terhitung sebagai
pendapatan maupun beban.

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
2. `build_template.py` menurunkan `EXP_ROW` dari urutan `KAT_EXPENSE`; kalau
   nama kategori berubah, kunci `EXP_ROW` ikut berubah. Jangan menulis nama
   kategori sebagai literal di sana.
3. Setelah mengubah daftar, jalankan:
   ```bash
   DATASET_DIR="/path/ke/Cash Report dan Mutasi Rekening" pytest tests/ -v
   python cash_report/verify_template.py
   ```
   Tes pertama membandingkan daftar dengan file Excel asli; tes kedua memeriksa
   template Google Sheets yang sudah dibangun.
4. Template Google Sheets yang sudah ada perlu dibangun ulang
   (`build_template.py`) karena isi sheet SETUP adalah nilai statis.
