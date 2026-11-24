"""Konfigurasi bersama untuk evaluasi SC-01.

Semua nilai dibaca dari `.env` di akar repo, sehingga tidak perlu mengekspor
variabel manual setiap kali menjalankan test. Variabel lingkungan yang sudah ada
tetap menang, berguna untuk CI atau saat ingin menimpa sementara.

Kunci yang dikenali:

    SC01_PAIRS        daftar pasangan gambar -> baris (CSV)
    SC01_IMAGES       folder gambar bukti transaksi
    GITHUB_TOKEN      dipakai hanya oleh `--download` untuk mengunduh dataset
                      dari repo privat
    GITHUB_DATASET_REPO   default: Project-Rework-G3-AI/rework-ai-finance-assistant-dataset
    GITHUB_DATASET_DIR    folder dataset di dalam repo tersebut

Kedua kunci SC01_* punya nilai bawaan yang masuk akal, jadi `.env` baru dari
`.env.example` sudah bisa dipakai tanpa disunting lebih dulu.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

AKAR = Path(__file__).resolve().parents[1]

# Repo dataset bersifat privat: berisi bukti transaksi perusahaan. Jangan
# dipindahkan ke repo aplikasi yang publik, dan jangan pakai repo pribadi
# seseorang — semua anggota kelompok harus bisa mengaksesnya.
REPO_DATASET = os.getenv(
    "GITHUB_DATASET_REPO", "Project-Rework-G3-AI/rework-ai-finance-assistant-dataset"
).strip()
# Folder dataset di dalam repo tersebut. Kosong berarti berkas ada di akar repo.
DIR_DATASET = os.getenv("GITHUB_DATASET_DIR", "").strip()
BRANCH_DATASET = os.getenv("GITHUB_DATASET_BRANCH", "main").strip()
SUB_DIR_IMAGES = "Bukti Transaksi Januari 2026"
SUB_DIR_PAIRS = "sc01/sc01_pairs.csv"

# Nilai bawaan: mengikuti susunan folder yang dibuat `--download`.
DEFAULT_PAIRS = "dataset/sc01/sc01_pairs.csv"
DEFAULT_IMAGES = "dataset/Bukti Transaksi Januari 2026"


def muat_env() -> None:
    """Muat `.env` di akar repo tanpa menimpa variabel yang sudah ada."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv sudah jadi dependensi
        return
    load_dotenv(AKAR / ".env", override=False)


def _path(nilai: str) -> Path:
    p = Path(nilai).expanduser()
    return p if p.is_absolute() else (AKAR / p).resolve()


def pairs_file() -> Path:
    """Lokasi CSV daftar pasangan. Kembalikan nilai bawaan bila belum diatur."""
    nilai = os.getenv("SC01_PAIRS", "").strip() or DEFAULT_PAIRS
    return _path(nilai)


def images_dir() -> Path:
    """Folder gambar bukti transaksi. Kembalikan nilai bawaan bila belum diatur."""
    nilai = os.getenv("SC01_IMAGES", "").strip() or DEFAULT_IMAGES
    return _path(nilai)


def baca_pasangan(path: Path) -> list[dict]:
    """Baca daftar pasangan. Beri pesan jelas bila berkasnya belum ada."""
    if not Path(path).is_file():
        raise SystemExit(
            f"daftar pasangan belum ada: {path}\n"
            "Jalankan lebih dulu: python3 tests/sc01_harness.py --download"
        )
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if (r.get("file") or "").strip()]


def ready(abaikan_ai: bool = False) -> tuple[bool, str]:
    """Periksa kelengkapan sebelum menjalankan evaluasi.

    Mengembalikan (siap, alasan). Alasan selalu diisi agar pengguna tahu persis
    apa yang kurang, bukan sekadar "skip".
    """
    su = pairs_file()
    if not su.is_file():
        return False, (f"daftar pasangan belum ada: {su}. "
                       f"Jalankan: python3 tests/sc01_harness.py --download")

    folder = images_dir()
    if not folder.is_dir():
        return False, (f"folder gambar belum ada: {folder}. "
                       f"Jalankan: python3 tests/sc01_harness.py --download")

    if not abaikan_ai and not os.getenv("AI_API_KEY", "").strip():
        return False, "AI_API_KEY kosong; SC-01 mengukur model asli, bukan mock"

    baris = baca_pasangan(su)
    if not baris:
        return False, f"daftar pasangan kosong: {su}"

    hilang = [r["file"].strip() for r in baris
              if not (folder / r["file"].strip()).is_file()]
    if hilang:
        return False, (f"{len(hilang)} dari {len(baris)} gambar tidak ada di {folder}. "
                       f"Jalankan: python3 tests/sc01_harness.py --download")
    return True, f"{len(baris)} pasangan siap diuji"


def _token(nilai: str | None = None) -> str | None:
    """Token GitHub, bila ada. Repo dataset publik, jadi token tidak wajib.

    Dibiarkan opsional supaya anggota tidak perlu membuat token hanya untuk
    mengunduh data. Bila nanti repo dijadikan privat lagi, token tetap dipakai
    secara otomatis tanpa perubahan kode.
    """
    return (nilai or os.getenv("GITHUB_TOKEN", "")).strip() or None


def _ambil_berkas(jalur: str) -> bytes:
    """Ambil berkas, mencoba akses anonim lalu memakai token bila perlu.

    Repo dataset semestinya publik, jadi akses anonim biasanya cukup dan tidak
    memerlukan token. Bila repo ternyata privat, percobaan anonim menghasilkan
    404; token yang tersedia di .env dipakai supaya pengguna tidak perlu tahu
    detail itu.
    """
    token = _token()
    if token:
        try:
            return _ambil_github(jalur, None)
        except SystemExit:
            return _ambil_github(jalur, token)
    return _ambil_github(jalur, None)


def _jalur_repo(*bagian: str) -> str:
    """Rangkai jalur di dalam repo dataset, tanpa garis miring berlebih."""
    potong = [DIR_DATASET] if DIR_DATASET else []
    potong.extend(bagian)
    return "/".join(p.strip("/") for p in potong if p.strip("/"))


def _ambil_github(jalur: str, token: str | None = None) -> bytes:
    """Ambil satu berkas mentah dari repo dataset.

    Repo publik dilayani lewat `raw.githubusercontent.com`, yang tidak memakai
    kuota API. Cara ini perlu karena kuota anonim API GitHub hanya 60 permintaan
    per jam, sedangkan satu kali unduh butuh 66 permintaan.

    Bila token tersedia, API biasa dipakai supaya repo privat tetap bekerja.
    Galat HTTP diterjemahkan menjadi pesan yang bisa ditindaklanjuti, karena
    traceback `urllib` tidak memberi tahu apa yang harus dilakukan.
    """
    import urllib.error
    import urllib.parse
    import urllib.request

    if not token:
        url = (f"https://raw.githubusercontent.com/{REPO_DATASET}/"
               f"{BRANCH_DATASET}/{urllib.parse.quote(jalur)}")
        sumber = "raw.githubusercontent.com (tanpa token)"
    else:
        url = (f"https://api.github.com/repos/{REPO_DATASET}/contents/"
               f"{urllib.parse.quote(jalur)}")
        sumber = "API GitHub (dengan token)"

    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/vnd.github.raw")

    try:
        return urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SystemExit(
                f"berkas tidak ditemukan: {jalur}\n"
                f"  sumber : {sumber}\n"
                f"  repo   : {REPO_DATASET} (branch {BRANCH_DATASET})\n"
                "Kemungkinan penyebab:\n"
                "  1. Repo dataset sedang privat, sehingga akses tanpa token ditolak.\n"
                "     Isi GITHUB_TOKEN di .env, atau minta pemilik repo menjadikannya publik.\n"
                "  2. Nama repo atau branch berubah. Periksa GITHUB_DATASET_REPO\n"
                "     dan GITHUB_DATASET_BRANCH di .env."
            ) from None
        if e.code in (403, 429):
            raise SystemExit(
                f"akses ditolak atau kena batas kuota: HTTP {e.code}\n"
                f"  sumber : {sumber}\n"
                "Isi GITHUB_TOKEN di .env untuk memakai kuota akunmu sendiri."
            ) from None
        raise SystemExit(f"gagal mengunduh {jalur}: HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise SystemExit(
            f"tidak bisa menghubungi GitHub: {e.reason}\n"
            "Periksa koneksi internet, lalu jalankan ulang perintah yang sama."
        ) from None


def unduh_pasangan(tujuan: Path | None = None,
                   token: str | None = None) -> Path:
    """Unduh daftar pasangan dari repo dataset bila belum ada.

    `--download` butuh daftar pasangan untuk tahu gambar mana yang harus diambil,
    sedangkan daftar itu sendiri juga ada di repo yang sama. Fungsi ini memutus
    ketergantungan tersebut sehingga satu perintah cukup.
    """
    tujuan = tujuan or pairs_file()
    if tujuan.is_file() and tujuan.stat().st_size > 100:
        return tujuan

    tujuan.parent.mkdir(parents=True, exist_ok=True)
    print(f"mengunduh daftar pasangan ke: {tujuan}")
    tujuan.write_bytes(_ambil_berkas(_jalur_repo(SUB_DIR_PAIRS)))
    return tujuan


def unduh_gambar(tujuan: Path | None = None, token: str | None = None,
                 berkas: list[str] | None = None) -> tuple[int, int]:
    """Unduh gambar dataset dari repo. Kembalikan (baru, dilewati).

    Hanya dipakai sekali di awal. Setelah gambar ada di disk, evaluasi berjalan
    sepenuhnya offline terhadap folder itu.

    Galat dicatat lalu dilanjutkan, supaya satu berkas bermasalah tidak
    membatalkan seluruh unduhan. Ringkasannya dilaporkan di akhir.
    """
    tujuan = tujuan or images_dir()

    perlu = berkas or [r["file"].strip() for r in baca_pasangan(pairs_file())]
    tujuan.mkdir(parents=True, exist_ok=True)

    baru = lewat = gagal = 0
    pesan_galat = ""
    for i, nama in enumerate(perlu, 1):
        dst = tujuan / nama
        if dst.is_file() and dst.stat().st_size > 1000:
            lewat += 1
            continue
        try:
            dst.write_bytes(_ambil_berkas(_jalur_repo(SUB_DIR_IMAGES, nama)))
        except SystemExit as e:
            # Pesan sudah informatif; simpan sekali, jangan cetak 65 kali.
            pesan_galat = pesan_galat or str(e)
            gagal += 1
            continue
        except Exception as e:
            pesan_galat = pesan_galat or f"{type(e).__name__}: {e}"
            gagal += 1
            continue
        baru += 1
        if i % 20 == 0:
            print(f"  ... {i}/{len(perlu)}")

    if gagal:
        print(f"peringatan: {gagal} dari {len(perlu)} gambar gagal diunduh")
        if pesan_galat:
            print("  " + pesan_galat.replace("\n", "\n  "))
    return baru, lewat
