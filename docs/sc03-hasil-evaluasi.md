# Hasil evaluasi SC-03: waktu proses sampai tersimpan

Dokumen ini melaporkan hasil pengukuran kriteria keberhasilan SC-03 pada bot
pencatatan transaksi PT Lokal Komoditi Indonesia, Kelompok G3.

## Apa yang diukur

SC-03 mengukur **waktu** dari bukti transaksi diterima sampai hasilnya
**tersimpan**. Bukan mutu isi, bukan kebenaran kategori. Dua kriteria sebelumnya
mengukur mutu; kriteria ini mengukur kecepatan.

Rantai yang diukur, berurutan:

```
terima gambar → ekstraksi AI → dedupe Sheets → unggah Drive → tulis baris → balas Telegram
```

## Target

**Kurang dari 5 detik.**

Angka ini berasal dari catatan turunan sesi sebelumnya, bukan dari BRD yang bisa
dibaca ulang. BRD di Drive masih berupa template kosong pada bagian *Success
Criteria*, sehingga target tidak bisa diverifikasi langsung ke dokumen. Ini
disebutkan supaya sumbernya jelas: bila BRD yang terisi ditemukan dan angkanya
berbeda, laporan ini harus diperbarui.

## Dua definisi waktu, dan mana yang dinilai

Ada dua cara membaca "sampai tersimpan", dan keduanya berbeda angka:

| Definisi | Berhenti di | Dipakai menilai target? |
|---|---|---|
| Dokumen (BRD) | baris masuk ke Sheets | **ya** |
| Pengguna | balasan diterima di Telegram | tidak, dilaporkan sebagai angka lain |

Definisi pengguna lebih ketat karena menambah perjalanan pulang-pergi Telegram.
Keduanya diukur dan dilaporkan terpisah, tidak ada yang disembunyikan.

## Di mana pengukuran dilakukan

Di **folder Drive sandbox**, bukan folder Cash Report perusahaan. Alasannya:
pengukuran menulis baris sungguhan, dan menulis baris uji ke ledger perusahaan
akan mencemari data keuangan riil.

Yang dipakai apa adanya dari produksi:

- `main.extract()` — panggilan model sungguhan
- `main.write_cash_report()` — dedupe, unggah Drive, tulis Sheets

Yang diganti, dan alasannya:

| Bagian | Diganti dengan | Alasan |
|---|---|---|
| Klien Sheets | OAuth user | Di mesin ini tidak ada service account |
| Klien Drive | OAuth user | `GOOGLE_OAUTH_REFRESH_TOKEN` tidak ada di mesin ini |
| Telegram | di-mock | Tidak ada bot token; mengirim pesan ke orang lain bukan bagian pengukuran |
| Folder tujuan | sandbox | Data perusahaan tidak boleh tercemar |

Karena Telegram di-mock, tahap `reply` **tidak diukur sungguhan**. Laporan
menuliskannya sebagai "tidak diukur", bukan "0,00 detik". Angka nol akan
terbaca sebagai "Telegram instan", padahal yang terjadi adalah tahap itu tidak
pernah dijalankan.

## Hasil

Diukur pada **65 gambar**, satu run, 24 November 2026.

| Ukuran | Nilai |
|---|---|
| **Rata-rata sampai tersimpan** | **10,31 detik** |
| Median | 8,50 detik |
| Persentil 90 | 15,10 detik |
| Tercepat | 5,30 detik |
| Terlambat | 44,75 detik |
| Lewat 5 detik | **65 dari 65 gambar** |

**Status: BELUM TERCAPAI.** Target 5 detik, hasil 10,31 detik — lebih dari dua
kali lipat.

Yang perlu dibaca dari tabel itu: **tidak ada satu pun gambar yang memenuhi
target.** Bahkan yang tercepat, 5,30 detik, masih di atas 5 detik. Jadi ini bukan
kasus "sebagian besar lulus, beberapa meleset" — seluruhnya meleset.

Median 8,50 detik lebih rendah dari rata-rata 10,31 detik, artinya sebarannya
menceng ke kanan: beberapa gambar sangat lambat dan menarik rata-rata naik.
Yang terlambat 44,75 detik hampir 9 kali target.

## Temuan: waktu habis di mana

Pecahan tahap adalah bagian terpenting dari laporan ini, karena rata-rata saja
tidak memberi tahu apa yang harus diperbaiki.

| Tahap | Rata-rata | Median | Porsi |
|---|---|---|---|
| `extract` | 8,31 detik | 6,52 detik | **81%** |
| `dedupe` | 1,68 detik | 1,65 detik | 16% |
| `append` | 0,32 detik | 0,31 detik | 3% |
| `upload` | 0,00 detik | 0,00 detik | 0% (Drive tidak aktif) |
| `reply` | tidak diukur | — | Telegram di-mock |

**Waktu habis di ekstraksi AI, bukan di penyimpanan.** 81% dari total waktu
adalah panggilan model. Ini penting karena mengubah kesimpulan: memperbaiki
kode penyimpanan tidak akan membawa angka ke bawah 5 detik.

Bahkan bila `dedupe` dan `append` dibuat gratis, sisanya tetap 8,31 detik.
Artinya target 5 detik **tidak bisa dicapai** tanpa mengubah cara model dipanggil
— misalnya model yang lebih cepat, atau ekstraksi yang dijalankan asinkron
sementara pengguna sudah menerima balasan.

### `dedupe` memanggil empat API untuk setiap baris

`main.py:363-371` menjalankan empat panggilan berurutan sebelum satu baris
ditulis:

```python
_find_or_create_folder(year, CR_FOLDER_ID)        # 1 panggilan Drive
_find_or_create_spreadsheet(year, year_folder)    # 1 panggilan Drive
_open_spreadsheet(spreadsheet_id)                 # 1 panggilan Sheets
ws.col_values(9)                                  # baca SELURUH kolom Ref ID
```

Tiga panggilan pertama menghasilkan nilai yang **sama setiap kali** untuk tahun
yang sama, tetapi dicari ulang dari nol pada setiap baris.

`col_values(9)` membaca seluruh kolom Ref ID hanya untuk memeriksa satu ID.
Kolom itu bertambah setiap transaksi, jadi biayanya **naik seiring waktu**:
semakin lama dipakai, semakin lambat.

Pengukuran awal menunjukkan `dedupe` 6,38 detik saat folder dan spreadsheet belum
ada, lalu turun ke sekitar 1,7 detik setelah keduanya ada. Artinya biaya besar
pertama kali itu wajar, tetapi 1,7 detik per baris untuk pekerjaan yang hasilnya
tidak berubah tetap pemborosan.

**Ini dicatat sebagai temuan, bukan diperbaiki.** Memperbaiki caching sebelum
mengukur akan mengubah yang diukur, dan angka sebelum-perbaikan adalah bukti yang
dibutuhkan Bug Log.

## Batas pengukuran

1. **65 gambar, bukan 118.** Hanya 65 foto yang punya acuan di `pairs.csv`.
   Sisanya tidak punya pembanding, jadi tidak dipakai. Ini angka 65 gambar.
2. **Telegram di-mock.** Definisi pengguna tidak terukur sungguhan.
3. **Drive tidak aktif** pada pengukuran ini, sehingga tahap `upload` bernilai
   nol. Bila Drive aktif, waktu akan lebih lama.
4. **Latensi penyedia model bervariasi.** Satu gambar bisa 5 detik, gambar lain
   45 detik, tanpa perbedaan ukuran berkas yang jelas. Karena itu median dan
   persentil 90 dilaporkan bersama rata-rata.

## Cara menjalankan ulang

```bash
python3 tests/_sc03_run.py            # melanjutkan yang belum terukur
python3 tests/_sc03_run.py --restart  # ukur ulang dari nol
python3 tests/_sc03_run.py --limit 5  # coba cepat pada 5 gambar
```

Waktu tidak bisa dihitung ulang dari hasil ekstraksi, berbeda dari SC-01 dan
SC-02. `--metrics-only` tidak berlaku untuk SC-03.

## Berkas

| Berkas | Isi |
|---|---|
| `tests/sc03_latency.py` | aturan penilaian, dua definisi waktu, penyusunan laporan |
| `tests/test_sc03_latency.py` | 17 test yang mengunci aturan penilaian |
| `tests/_sc03_probe.py` | harness pengukuran rantai produksi |
| `tests/_sc03_run.py` | menjalankan pengukuran pada banyak gambar |
| `sc-out/sc03_samples.csv` | satu baris per gambar, termasuk pecahan tahap |
| `sc-out/sc03_report.txt` | laporan teks |
| `sc-out/sc03_metrics.json` | ringkasan dalam bentuk JSON |
