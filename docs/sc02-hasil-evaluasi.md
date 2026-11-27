# SC-02 — Hasil evaluasi kelengkapan field wajib

Dokumen ini mencatat hasil pengukuran kriteria keberhasilan **SC-02** pada BRD:
persentase field wajib yang **terbaca** dari gambar bukti transaksi.

**Target BRD:** minimal 90%.

## Apa yang diukur, dan apa yang tidak

SC-02 hanya menjawab satu pertanyaan: **apakah field wajibnya terbaca**.

Apakah nilainya benar **bukan** urusan SC-02. Nilai `nominal` 20.000 yang
terbaca 50.000 tetap dihitung lengkap. Kecocokan isi diukur di SC-01 untuk
kategori, dan sengaja tidak diukur di sini untuk field lain.

Pemisahan itu bukan pelonggaran. Kalau SC-02 ikut menilai kebenaran isi, satu
field yang merosot (kategori, 9,2%) akan menyeret kriteria yang seharusnya
mengukur hal lain, dan kegagalan yang sama dilaporkan dua kali.

## Hasil

| Ukuran | Nilai | Target | Status |
|---|---|---|---|
| **Kelengkapan rata-rata (5 field)** | **93,5%** | 90% | **tercapai** |
| Baris dengan 5/5 field lengkap | 49 dari 65 (75,4%) | — | angka pendukung |

**Angka yang dibandingkan dengan target adalah kelengkapan rata-rata 93,5%.**

Angka pendukung 49/65 ditampilkan karena ia menjawab pertanyaan berbeda: bukan
"berapa persen sel yang terisi", melainkan "berapa gambar yang tidak perlu
diperiksa ulang sama sekali". Keduanya perlu disebut supaya pembaca tidak
menyangka 93,5% berarti hampir semua gambar bersih.

Rata-rata dihitung **per field**, bukan per baris, supaya satu field yang selalu
gagal tidak tertutup empat field yang selalu berhasil.

## Rincian per field

| Field | Terbaca | Kelengkapan | Diisi tebakan |
|---|---|---|---|
| `tanggal` | 64 / 65 | 98,5% | 0 |
| `nominal` | 64 / 65 | 98,5% | 0 |
| `kantong` (`bank`) | **49 / 65** | **75,4%** | 15 |
| `arah` | 64 / 65 | 98,5% | 0 |
| `kategori` | 63 / 65 | 96,9% | 1 |

**Satu field masih menahan kriteria:** `kantong`, dengan 75,4%.

Kalau `kantong` sempurna, kelengkapan jadi (98,5 + 98,5 + 100 + 98,5 + 96,9) / 5 = 98,5%.

## Perbandingan dengan pengukuran sebelumnya

| Field | 25 November (prompt lama) | 27 November (prompt sekarang) |
|---|---|---|
| `tanggal` | 64 / 65 | 64 / 65 |
| `nominal` | 64 / 65 | 64 / 65 |
| `kantong` | **37 / 65 (56,9%)** | **49 / 65 (75,4%)** |
| `arah` | 64 / 65 | 64 / 65 |
| `kategori` | 64 / 65 | 63 / 65 |
| **Kelengkapan rata-rata** | **90,2%** | **93,5%** |
| Baris lengkap 5/5 | 37 dari 65 | **49 dari 65** |

Kenaikan terbesar ada pada `kantong`, dari 56,9% menjadi 75,4%, setelah prompt
mengganti `TUNAI` menjadi `UANG KAS` dan menegaskan bahwa `kantong_tujuan`
wajib terisi saat `arah=transfer`. `kategori` turun satu baris karena satu
gambar gagal dibaca model dan jatuh ke mode cadangan.

Kedua angka tetap di atas target 90%, tetapi **marginnya sekarang lebih lebar**:
3,5 poin, bukan 0,2 poin seperti pada pengukuran lama.

## Kenapa `kantong` gagal 16 kali

Bukan karena model lemah. Bukti transfer **tidak mencetak rekening asal**.

Diperiksa langsung pada lima gambar:

| Gambar | Yang tercetak | Bank asal tercetak? |
|---|---|---|
| `photo_2026-01-05_11-22-59.jpg` | BCA → BNI | tidak |
| `photo_2026-01-02_11-20-19.jpg` | BNI, "Bank Tujuan: BNI" | tidak |
| `photo_2026-01-09_21-02-41.jpg` | BNI, "Bank Tujuan: BNI" | tidak |
| `photo_2026-01-06_14-26-54.jpg` | Flip → BRI | tidak |
| `photo_2026-01-17_11-48-12.jpg` | tiket kereta KAI | tidak |

Prompt produksi yang dipakai pada pengukuran 25 November memberi izin
mengosongkan:

```
"bank":"kantong asal dana — salah satu dari: BRI, BNI, Jago, TUNAI;
 kosong bila tidak terbaca"
```

Prompt itu menghasilkan 28 gambar tanpa `kantong`. Setelah prompt diperbaiki
pada 26 dan 27 November, jumlahnya turun menjadi **16 gambar**:

```
"bank":"kantong asal dana — salah satu dari: BRI, BNI, Jago, UANG KAS;
 kosong bila tidak terbaca"
"kantong_tujuan":"WAJIB terisi bila arah=transfer — ..."
```

Perbaikannya bukan menghapus izin mengosongkan, melainkan menegaskan bahwa
`kantong_tujuan` wajib terisi saat `arah=transfer` dan mengganti istilah `TUNAI`
menjadi `UANG KAS` agar sesuai template. Hasilnya, 12 gambar yang sebelumnya
gagal kini terbaca.

Sisanya, 16 gambar, tetap gagal karena **informasinya memang tidak ada di
gambar** — bukan karena model atau prompt. Selama bukti transfer tidak mencetak
rekening asal, field ini tidak dapat dicapai 100% tanpa sumber data lain.

Kebocoran yang mengikutinya dicatat terpisah di
[`bug-kantong-tunai.md`](bug-kantong-tunai.md): kolom Kantong di sheet selalu
terisi nilai bawaan `UANG KAS`, sehingga transaksi yang kantong asalnya tidak
terbaca tercatat seolah berasal dari kas.

## Kenapa `tanggal`, `nominal`, `arah` 64/65, `kategori` 63/65, dan `kantong` 49/65

**Satu gambar jatuh ke mode cadangan:** `photo_2026-01-05_09-57-49.jpg`. Model
dipanggil, menunggu 280 detik, lalu membalas kosong. Karena mode `mock` berarti
tidak ada field yang terbaca dari model, kelima field dihitung gagal untuk baris
itu. Ini satu-satunya penyebab `nominal` gagal.

**`kategori` gagal dua kali**, dengan sebab berbeda:

| Gambar | Sebab |
|---|---|
| `photo_2026-01-05_09-57-49.jpg` | mode cadangan, kategori kosong |
| `photo_2026-01-24_10-50-38.jpg` | model menjawab di luar daftar kategori, sehingga ditandai `Perlu Ditinjau` |

**`kantong` gagal 16 kali**, seluruhnya karena rekening asal tidak tercetak pada
bukti transfer. Rinciannya ada di bagian sebelumnya.

`tanggal` dan `arah` hanya gagal pada satu gambar yang sama, yaitu baris mode
cadangan.

## Cara memeriksa kelengkapan tanpa tertipu nilai bawaan

`main.extract` mengisi nilai bawaan saat model gagal membaca:

```
tanggal kosong -> tanggal hari ini
arah kosong    -> "keluar"
bank kosong    -> CR_DEFAULT_BANK ("UANG KAS")
kategori asing -> "Perlu Ditinjau"
```

Kalau kelengkapan diukur dengan "field kosong atau tidak", hasilnya mendekati
100% padahal model tidak membaca apa pun. Karena itu penilaian memakai dua
sinyal yang tidak bisa dipalsukan nilai bawaan:

1. **`catatan`** — `main.py:194–212` menulis `"nominal tidak terbaca — isi
   manual"` dan sejenisnya. Ini sinyal paling langsung, karena berasal dari kode
   yang tahu bedanya "model tidak menjawab" dan "model menjawab nilai".
2. **`mode`** — `mock` berarti model tidak dipanggil atau gagal total.

Nilai acuan dari dataset **tidak** dipakai. Membandingkan dengan acuan adalah
pengukuran kebenaran isi, bukan kelengkapan.

Aturan ini dikunci test: `test_unreadable_field_is_not_rescued_by_the_default_value`,
`test_date_filled_with_today_still_counts_as_unreadable`,
`test_wrong_but_present_value_is_still_complete`, dan
`test_reference_is_ignored_even_when_provided`.

## Cara menjalankan

```bash
python3 tests/sc_runner.py --sc02
```

Butuh `sc-out/results_per_row.csv` yang diisi pengukuran SC-01 (memanggil model,
berbiaya). Menilai ulang **tidak** memanggil model lagi: cukup ubah aturan dan
baca ulang berkas yang sama.

Berkas keluaran: `sc-out/sc02_report.txt` dan `sc-out/sc02_metrics.json`.

Pengukuran terbaru dijalankan pada **27 November 2026** dengan 65 panggilan
model `deepseek/deepseek-v4.1-flash-1017`, memakai prompt produksi setelah
perubahan `UANG KAS` dan aturan `arah=transfer`.

## Batas pengukuran

- Yang diukur hanya **keberadaan** field, bukan kebenaran isinya.
- Kebenaran kantong asal tidak terdeteksi di sini; lihat
  [`bug-kantong-tunai.md`](bug-kantong-tunai.md).
- `kantong` tidak dapat mencapai 100% selama bukti transfer tidak mencetak
  rekening asal. Batas ini berasal dari data, bukan dari kemampuan model.
- BRD menyebut field wajib *(tanggal, nominal, kantong asal dana, arah,
  kategori)*, dan kelimanya sudah diukur di sini. Definisi lama BRD yang
  menyebut `pihak` sudah diperbarui; selisih lain dicatat di
  [`brd-yang-perlu-disesuaikan.md`](brd-yang-perlu-disesuaikan.md).
- Dataset uji 65 gambar, bukan 118 seperti tertulis di BRD.
