# Contoh mutasi bank (sintetis)

Dua PDF uji untuk rekonsiliasi (milestone 2) — **akun dummy, bukan rekening
asli**; nominal mengikuti transaksi Cash Report Januari2026 supaya hasil
matching-nya bisa diprediksi.

| File | Akun dummy | Hasil yang diharapkan |
|---|---|---|
| `mutasi_BNI_match.pdf` | BNI `0012345678` | `matched:6, bank_only:0, sheet_only:0` |
| `mutasi_BRI_tidak_match.pdf` | BRI `0098765432` | `matched:1, bank_only:2, sheet_only:1` |

Cara pakai: set env `BNI_ACCOUNT_NUMBER=0012345678` dan
`BRI_ACCOUNT_NUMBER=0098765432` (lokal atau Render), lalu kirim file ke bot
atau `POST /api/reconcile` dengan `pdf_base64`.

Jago: `2100012345` (belum ada contoh file — tidak ada baris Jago di data uji).

Catatan: aman untuk repo privat; jangan dipush ke repo publik (nominal adalah
data transaksi nyata).
