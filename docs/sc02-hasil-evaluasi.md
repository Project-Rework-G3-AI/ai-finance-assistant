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
field yang merosot (kategori, 7,7%) akan menyeret kriteria yang seharusnya
mengukur hal lain, dan kegagalan yang sama dilaporkan dua kali.

## Hasil

| Ukuran | Nilai | Target | Status |
|---|---|---|---|
| **Kelengkapan rata-rata (5 field)** | **90,2%** | 90% | **tercapai** |
| Baris dengan 5/5 field lengkap | 37 dari 65 (56,9%) | — | angka pendukung |

**Angka yang dibandingkan dengan target adalah kelengkapan rata-rata 90,2%.**

Angka pendukung 37/65 ditampilkan karena ia menjawab pertanyaan berbeda: bukan
"berapa persen sel yang terisi", melainkan "berapa gambar yang tidak perlu
diperiksa ulang sama sekali". Keduanya perlu disebut supaya pembaca tidak
menyangka 90,2% berarti hampir semua gambar bersih.

Rata-rata dihitung **per field**, bukan per baris, supaya satu field yang selalu
gagal tidak tertutup empat field yang selalu berhasil.

## Rincian per field

| Field | Terbaca | Kelengkapan | Diisi tebakan |
|---|---|---|---|
| `tanggal` | 64 / 65 | 98,5% | 0 |
| `nominal` | 64 / 65 | 98,5% | 0 |
| `kantong` (`bank`) | **37 / 65** | **56,9%** | 27 |
| `arah` | 64 / 65 | 98,5% | 0 |
| `kategori` | 64 / 65 | 98,5% | 0 |

**Satu field menahan seluruh kriteria:** `kantong`, dengan 56,9%.

Kalau `kantong` sempurna, kelengkapan jadi (98,5 × 4 + 100) / 5 = 98,8%.

## Kenapa `kantong` gagal 28 kali

Bukan karena model lemah. Bukti transfer **tidak mencetak rekening asal**.

Diperiksa langsung pada lima gambar:

| Gambar | Yang tercetak | Bank asal tercetak? |
|---|---|---|
| `photo_2026-01-05_11-22-59.jpg` | BCA → BNI | tidak |
| `photo_2026-01-02_11-20-19.jpg` | BNI, "Bank Tujuan: BNI" | tidak |
| `photo_2026-01-09_21-02-41.jpg` | BNI, "Bank Tujuan: BNI" | tidak |
| `photo_2026-01-06_14-26-54.jpg` | Flip → BRI | tidak |
| `photo_2026-01-17_11-48-12.jpg` | tiket kereta KAI | tidak |

Prompt produksi memberi izin mengosongkan:

```
"bank":"kantong asal dana — salah satu dari: BRI, BNI, Jago, TUNAI;
 kosong bila tidak terbaca"
```

Model mematuhi instruksi itu pada 28 gambar. Dari 28 itu, **13 berarah
`transfer` dan kantong tujuannya terbaca** — artinya model menemukan bank tujuan
dan dengan jujur menyatakan bank asal tidak ada.

Kebocoran yang mengikutinya dicatat terpisah di
[`bug-kantong-tunai.md`](bug-kantong-tunai.md): kolom Kantong di sheet selalu
terisi `TUNAI` oleh nilai bawaan, sehingga 12 transaksi tercatat keluar dari kas
tunai padahal dananya bukan tunai.

## Kenapa `tanggal`, `nominal`, `arah`, `kategori` masing-masing 64/65

Satu gambar dijalankan dalam **mode `mock`**, bukan `vision`. Nama berkasnya
dapat dilihat di `sc-out/sc02_report.txt`. Mode mock berarti model tidak
dipanggil atau gagal total, jadi tidak ada field yang terbaca dari model dan
kelima field dihitung gagal untuk baris itu.

Itu satu-satunya penyebab. Di 64 gambar lain, keempat field tersebut terbaca
semuanya.

## Cara memeriksa kelengkapan tanpa tertipu nilai bawaan

`main.extract` mengisi nilai bawaan saat model gagal membaca:

```
tanggal kosong -> tanggal hari ini
arah kosong    -> "keluar"
bank kosong    -> CR_DEFAULT_BANK ("TUNAI")
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

## Batas pengukuran

- Yang diukur hanya **keberadaan** field, bukan kebenaran isinya.
- Kebenaran kantong asal tidak terdeteksi di sini; lihat
  [`bug-kantong-tunai.md`](bug-kantong-tunai.md).
- BRD menyebut field wajib *(tanggal, nominal, pihak)*, sedangkan kode mengukur
  lima field dan `pihak` tidak ada sama sekali. Selisih definisi itu dicatat di
  [`brd-yang-perlu-disesuaikan.md`](brd-yang-perlu-disesuaikan.md).
- Dataset uji 65 gambar, bukan 118 seperti tertulis di BRD.
