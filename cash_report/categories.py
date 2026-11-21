"""Daftar kategori transaksi — sumber tunggal untuk seluruh repo.

Dipakai oleh main.py (prompt AI + validasi), build_template.py (sheet SETUP,
EXPENSE DETAIL, INCOME STATEMENT), dan cr.py.

Sumber nama:
  - SOP Pencatatan Uang Keluar (10 kategori pengeluaran, eksplisit di tabel)
  - Dropdown kolom KATEGORI pada Cash Report perusahaan (pemasukan + neraca)

Aturan:
  - Jangan mengubah string kategori tanpa memperbarui template, karena
    SUMIFS di RECAP/EXPENSE/INCOME mencocokkan string secara persis.
  - Nama yang tidak ada di daftar ini WAJIB dinormalkan lewat normalize()
    sebelum ditulis, atau ditandai PERLU_DITINJAU.
"""

# --- Pemasukan -------------------------------------------------------------
# SOP hanya mengatur uang keluar, jadi kategori pemasukan diambil dari dropdown
# Cash Report. Perusahaan memecah pendapatan usaha menjadi tiga.
PENDAPATAN = [
    "Pendapatan Usaha (Penjualan Produk)",
    "Pendapatan Usaha (Penjualan Lainnya)",
    "Pendapatan Usaha (Workshop)",
    "Pendapatan Lain",
]

# --- Perpindahan dana ------------------------------------------------------
# Bukan pendapatan dan bukan beban. Dikecualikan dari RECAP dan laba rugi,
# tetapi tetap dihitung di saldo per kantong.
PERPINDAHAN = [
    "Transfer Antar Bank",
]

# --- Neraca -----------------------------------------------------------------
NERACA = [
    "Persediaan",
    "Aset Tetap",
    "Utang/Piutang",
]

# --- Pengeluaran: 10 kategori dari SOP Pencatatan Uang Keluar ---------------
PENGELUARAN_SOP = [
    "Bahan Baku",                                    # pembelian bahan produksi
    "Biaya-Gaji Karyawan",                           # pembayaran gaji
    "Biaya-Konsumsi",                                # pembelian konsumsi
    "Biaya-Perlengkapan Kantor dan Administrasi",    # pembelian ATK
    "Biaya-Transportasi",                            # perjalanan & kendaraan kantor
    "Biaya-Ongkir",                                  # jasa pengiriman
    "Biaya-Perbaikan Bangunan",                      # perbaikan fasilitas
    "Biaya-Operasional",                             # listrik, air, internet, kebersihan
    "Biaya-Pembelian Aset",                          # pembelian peralatan/aset
    "Biaya-Sosial",                                  # bantuan/kegiatan sosial
]

# --- Pengeluaran tambahan: ada di dropdown, dipakai usaha ini --------------
PENGELUARAN_TAMBAHAN = [
    "Biaya-Pajak",
    "Biaya-Bunga Bank",
    "Biaya-Administrasi Flip dan Bank",
    # Rincian operasional yang dipakai perusahaan di tab Salinan. Dipisah dari
    # Biaya-Operasional karena perusahaan memang mencatatnya terpisah, dan
    # menyatukannya menghapus informasi yang sudah ada di data asli.
    "Biaya-Listrik dan Internet",
    "Biaya-R&D",
    "Biaya-Pelatihan",
    "Beban Lain",
]

# --- Saldo awal -------------------------------------------------------------
# Bukan transaksi, tetapi muncul di setiap sheet Cash Report sebagai baris
# pembuka dan dipakai 11 kali pada data Jan-Jul 2026. Harus dikenali supaya
# tidak jatuh ke PERLU_DITINJAU.
SALDO_AWAL = [
    "Saldo Awal",
]

# --- Penanda: bukan kategori akuntansi -------------------------------------
# Dipakai saat model tidak yakin. Sengaja dipisah supaya tidak menumpuk
# diam-diam bersama kategori sungguhan.
PERLU_DITINJAU = "Perlu Ditinjau"

KATEGORI = (
    SALDO_AWAL
    + PENDAPATAN
    + PERPINDAHAN
    + NERACA
    + PENGELUARAN_SOP
    + PENGELUARAN_TAMBAHAN
    + [PERLU_DITINJAU]
)

# Kategori yang boleh dipilih model. Dua yang dikecualikan:
#   - PERLU_DITINJAU : penanda, diisi kode saat model tidak yakin
#   - Saldo Awal     : baris pembuka buku, bukan transaksi yang difoto
KATEGORI_UNTUK_MODEL = [
    k for k in KATEGORI if k not in (PERLU_DITINJAU, "Saldo Awal")
]

# Teks siap tempel untuk prompt.
PROMPT_KATEGORI = ", ".join(KATEGORI_UNTUK_MODEL)

# --- Alias ------------------------------------------------------------------
# Varian ejaan/skema yang sah -> nama final. Mencakup:
#   - skema 'Beban Operasional-*' (tab Salinan BNI/BRI) -> 'Biaya-*' (SOP)
#   - typo pada file perusahaan dan pada cr.py
#   - nama ringkas yang mungkin dihasilkan model
ALIAS = {
    "Beban Operasional-Gaji Karyawan": "Biaya-Gaji Karyawan",
    "Beban Operasional-Listrik dan Internet": "Biaya-Listrik dan Internet",
    "Beban Operasional-Konsumsi": "Biaya-Konsumsi",
    "Beban Operasional - Perlengkapan Kantor dan Administrasi":
        "Biaya-Perlengkapan Kantor dan Administrasi",
    "Beban Operasional - Transportasi": "Biaya-Transportasi",
    "Beban Operasional-R&D": "Biaya-R&D",
    "Beban Operasional-RD": "Biaya-R&D",
    "Beban Operasional-Pelatihan": "Biaya-Pelatihan",
    "Biaya-Perlengkapan Kantor dan Aministrasi":
        "Biaya-Perlengkapan Kantor dan Administrasi",
    "Biaya-Transporrtasi": "Biaya-Transportasi",
    "Biaya Sosial": "Biaya-Sosial",
    "Pajak": "Biaya-Pajak",
    "Bunga": "Biaya-Bunga Bank",
    "Bunga Bank": "Biaya-Bunga Bank",
    "Administrasi Bank": "Biaya-Administrasi Flip dan Bank",
    "Admin Flip": "Biaya-Administrasi Flip dan Bank",
    "Admin Bank": "Biaya-Administrasi Flip dan Bank",
    "Penjualan": "Pendapatan Usaha (Penjualan Produk)",
    "Penjualan Produk": "Pendapatan Usaha (Penjualan Produk)",
    "Penjualan Lainnya": "Pendapatan Usaha (Penjualan Lainnya)",
    "Workshop": "Pendapatan Usaha (Workshop)",
    "Lainnya": PERLU_DITINJAU,
    "Lain-lain": PERLU_DITINJAU,
    "Tidak diketahui": PERLU_DITINJAU,
}


def normalize(nilai):
    """Kembalikan nama kategori final, atau PERLU_DITINJAU bila tidak dikenali.

    Tidak pernah mengembalikan None: baris tanpa kategori tetap harus tercatat,
    hanya ditandai supaya bisa diperiksa manusia.
    """
    teks = " ".join(str(nilai or "").split()).strip()
    if teks in KATEGORI:
        return teks
    if teks in ALIAS:
        return ALIAS[teks]
    # bandingkan tanpa peduli huruf besar/kecil dan spasi berlebih
    rendah = teks.lower()
    for k in KATEGORI:
        if k.lower() == rendah:
            return k
    for a, t in ALIAS.items():
        if a.lower() == rendah:
            return t
    return PERLU_DITINJAU


def valid(nilai):
    """True bila nilai (setelah normalisasi) adalah kategori sungguhan."""
    return normalize(nilai) != PERLU_DITINJAU
