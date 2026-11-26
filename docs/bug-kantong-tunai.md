# Bug: transfer bukan kas tunai tercatat keluar dari kantong TUNAI

Dokumen ini mencatat satu cacat produksi yang ditemukan saat mengukur SC-06.
Cacat ini **bukan** angka SC-06 dan sengaja dipisahkan, supaya angka kriteria
tidak dipakai untuk menghukum hal yang tidak diukurnya.

## Ringkasan

Ketika model gagal membaca kantong asal dana, produksi mengisi kolom Kantong
dengan nilai bawaan `CR_DEFAULT_BANK` (`TUNAI`). Untuk transaksi transfer, ini
membuat baris "uang keluar dari TUNAI" padahal dananya bukan kas tunai.

| | |
|---|---|
| Gambar terdampak | **12 dari 65** (18,5%) |
| Baris sheet salah | **12 baris** (satu per gambar) |
| Sifat | data keuangan tercatat di kantong yang salah |
| Sudah disadari produksi? | ya, tapi hanya ditandai di balasan Telegram |

## Bukti kode

`main.py:425` — kolom Kantong selalu terisi:

```python
kantong = str(rec.get("bank") or "").strip().upper() or CR_DEFAULT_BANK
```

`main.py:62` — nilai bawaannya:

```python
CR_DEFAULT_BANK = os.getenv("CR_DEFAULT_BANK", "TUNAI").strip().upper()
```

`main.py:793` — produksi sudah tahu ini masalah, tapi hanya menyorotnya di
balasan Telegram, tidak di sheet:

```python
if not str(rec.get("bank") or "").strip():
    # Bukti: kantong default mengotori TUNAI/Kas Operasional (Q&A stakeholder:
    # kas operasional direkonsiliasikan ke buku kas fisik) — sorot di balasan.
    baris_kantong = (...)
```

Akibatnya: pembaca sheet melihat `TUNAI` tanpa penanda apa pun, sementara
pembaca balasan Telegram melihat peringatan. Dua tempat, dua cerita.

## Kenapa ini terjadi

Bukti transfer **tidak mencetak rekening asal**. Diperiksa langsung pada lima
gambar:

| Gambar | Isi gambar | Bank asal tercetak? |
|---|---|---|
| `photo_2026-01-05_11-22-59.jpg` | BCA → BNI, tujuan a.n. ILHAM NAWAN RASYID | tidak |
| `photo_2026-01-02_11-20-19.jpg` | BNI, "Bank Tujuan: BNI" | tidak |
| `photo_2026-01-09_21-02-41.jpg` | BNI, "Bank Tujuan: BNI" | tidak |
| `photo_2026-01-06_14-26-54.jpg` | Flip → BRI | tidak |
| `photo_2026-01-17_11-48-12.jpg` | tiket kereta KAI | tidak |

Prompt produksi menyuruh model mengosongkan field bila tidak terbaca:

```
"bank":"kantong asal dana — salah satu dari: BRI, BNI, Jago, TUNAI;
 kosong bila tidak terbaca"
```

Model mematuhi instruksi itu: pada 28 gambar `bank` dikembalikan sebagai string
kosong, bukan dihilangkan kuncinya.

Dari 28 gambar itu, 13 berarah `transfer` dan **kantong tujuannya terbaca**.
Artinya model membaca gambar dengan benar; ia hanya tidak menemukan informasi
yang memang tidak ada.

## 12 transaksi yang mencatat "keluar dari TUNAI"

| # | Berkas | Baris 1 (keluar) | Baris 2 (masuk) |
|---:|---|---|---|
| 1 | `photo_2026-01-05_11-22-59.jpg` | TUNAI | BNI |
| 2 | `photo_2026-01-06_09-27-39.jpg` | TUNAI | BNI |
| 3 | `photo_2026-01-06_14-26-54.jpg` | TUNAI | BRI |
| 4 | `photo_2026-01-08_09-21-46.jpg` | TUNAI | BNI |
| 5 | `photo_2026-01-08_18-54-01.jpg` | TUNAI | BNI |
| 6 | `photo_2026-01-09_15-53-31.jpg` | TUNAI | BRI |
| 7 | `photo_2026-01-16_10-32-23.jpg` | TUNAI | BRI |
| 8 | `photo_2026-01-20_09-39-28.jpg` | TUNAI | BNI |
| 9 | `photo_2026-01-20_11-05-55.jpg` | TUNAI | BRI |
| 10 | `photo_2026-01-20_11-10-51.jpg` | TUNAI | BNI |
| 11 | `photo_2026-01-22_19-13-28.jpg` | TUNAI | BNI |
| 12 | `photo_2026-01-24_10-50-38.jpg` | TUNAI | BNI |

Sisanya (16 gambar) menulis satu baris saja, jadi tidak menghasilkan pasangan
palsu, tetapi kolom Kantong-nya tetap berisi `TUNAI` yang belum tentu benar.

## Dampak

- **Kas tunai berkurang** padahal tidak ada uang tunai keluar.
- **Saldo rekening asal tidak tercatat** sama sekali, sehingga rekonsiliasi per
  kantong tidak bisa dipercaya.
- Laporan per kantong (yang menjadi inti cash report) menjadi salah untuk 12
  transaksi.

## Kenapa SC-06 tidak menghukum ini

Kalimat BRD untuk SC-06 memeriksa **keberadaan kolom**, bukan kebenaran isinya.
Kolom Kantong selalu terisi, jadi SC-06 tetap tercapai. Menjadikan cacat ini
sebagai angka SC-06 berarti mengukur hal di luar lingkup kriteria.

Pengukuran yang menangkapnya adalah **SC-02** (`bank` 54,8%).

## Pilihan perbaikan

Semua ada di sisi produksi, bukan testing. Belum ada yang dikerjakan.

1. **Bedakan "memang tunai" dari "tidak terbaca".** Jangan pakai `TUNAI` untuk
   dua makna. Misalnya kolom Kantong dibiarkan kosong dan `Catatan` diisi
   penanda, sehingga barisnya terlihat butuh diperiksa.
2. **Ambil kantong asal dari sumber lain.** Bukti transfer tidak mencetaknya,
   jadi perlu konteks admin yang mengunggah, atau pemetaan nomor rekening
   pengirim ke kantong.
3. **Jangan pecah transfer bila kantong asal tidak diketahui.** Saat ini baris
   keluar memakai `TUNAI`. Mencatat satu baris "masuk ke BNI" dengan catatan
   "asal tidak terbaca" lebih jujur daripada mengarang kantong asal.
4. **Ubah prompt** agar model menandai ketidakpastian alih-alih mengosongkan.
   Ini tidak menciptakan informasi yang tidak ada, jadi hanya menolong bila
   dikombinasikan dengan pilihan 2.

## Cara memeriksa ulang

```bash
python3 tests/_sc06_run.py            # ambil balasan model (berbiaya)
python3 - <<'PY'
import csv, json, sys
sys.path.insert(0, "tests")
import sc06_mapping as s, main
for r in csv.DictReader(open("sc-out/sc06_samples.csv")):
    if r["ok"] != "ya":
        continue
    raw = json.loads(r["raw"])
    if str(raw.get("bank") or "").strip():
        continue
    baris = s.written_rows(raw)
    if len(baris) == 2:
        print(r["file"], "->", baris[0][1], "keluar /", baris[1][1], "masuk")
PY
```
