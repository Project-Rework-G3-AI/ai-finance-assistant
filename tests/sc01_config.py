"""Konfigurasi bersama untuk evaluasi SC-01.

Semua nilai dibaca dari `.env` di akar repo, sehingga tidak perlu mengekspor
variabel manual setiap kali menjalankan test. Variabel lingkungan yang sudah ada
tetap menang, berguna untuk CI atau saat ingin menimpa sementara.

Kunci yang dikenali:

    SC01_PAIRS        daftar pasangan gambar -> baris (CSV)
    SC01_IMAGES       folder gambar bukti transaksi
    GITHUB_TOKEN      dipakai hanya oleh `--download` untuk mengunduh dataset
                      dari repo privat
    GITHUB_DATASET_REPO   default: NafisHandoko/rework-ai-finance-assistant-dataset
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
    "GITHUB_DATASET_REPO", "NafisHandoko/rework-ai-finance-assistant-dataset"
).strip()
# Folder dataset di dalam repo tersebut. Kosong berarti berkas ada di akar repo.
DIR_DATASET = os.getenv("GITHUB_DATASET_DIR", "").strip()
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


def _token(nilai: str | None = None) -> str:
    token = (nilai or os.getenv("GITHUB_TOKEN", "")).strip()
    if not token:
        raise SystemExit(
            "GITHUB_TOKEN kosong. Tambahkan ke .env untuk mengunduh dataset privat.\n"
            "Butuh token dengan akses baca ke " + REPO_DATASET
        )
    return token


def _jalur_repo(*bagian: str) -> str:
    """Rangkai jalur di dalam repo dataset, tanpa garis miring berlebih."""
    potong = [DIR_DATASET] if DIR_DATASET else []
    potong.extend(bagian)
    return "/".join(p.strip("/") for p in potong if p.strip("/"))


def _ambil_github(jalur: str, token: str) -> bytes:
    """Ambil satu berkas mentah dari repo dataset privat."""
    import urllib.parse
    import urllib.request

    url = (f"https://api.github.com/repos/{REPO_DATASET}/contents/"
           f"{urllib.parse.quote(jalur)}")
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github.raw")
    return urllib.request.urlopen(req, timeout=60).read()


def unduh_pasangan(tujuan: Path | None = None,
                   token: str | None = None) -> Path:
    """Unduh daftar pasangan dari repo privat bila belum ada.

    `--download` butuh daftar pasangan untuk tahu gambar mana yang harus diambil,
    sedangkan daftar itu sendiri juga ada di repo privat. Fungsi ini memutus
    ketergantungan tersebut sehingga satu perintah cukup.
    """
    tujuan = tujuan or pairs_file()
    if tujuan.is_file() and tujuan.stat().st_size > 100:
        return tujuan

    token = _token(token)
    tujuan.parent.mkdir(parents=True, exist_ok=True)
    print(f"mengunduh daftar pasangan ke: {tujuan}")
    tujuan.write_bytes(_ambil_github(_jalur_repo(SUB_DIR_PAIRS), token))
    return tujuan


def unduh_gambar(tujuan: Path | None = None, token: str | None = None,
                 berkas: list[str] | None = None) -> tuple[int, int]:
    """Unduh gambar dataset dari repo privat. Kembalikan (baru, dilewati).

    Hanya dipakai sekali di awal. Setelah gambar ada di disk, evaluasi berjalan
    sepenuhnya offline terhadap folder itu.
    """
    token = _token(token)
    tujuan = tujuan or images_dir()

    perlu = berkas or [r["file"].strip() for r in baca_pasangan(pairs_file())]
    tujuan.mkdir(parents=True, exist_ok=True)

    baru = lewat = gagal = 0
    for i, nama in enumerate(perlu, 1):
        dst = tujuan / nama
        if dst.is_file() and dst.stat().st_size > 1000:
            lewat += 1
            continue
        try:
            dst.write_bytes(
                _ambil_github(_jalur_repo(SUB_DIR_IMAGES, nama), token))
        except Exception as e:
            print(f"  GAGAL {nama}: {str(e)[:70]}")
            gagal += 1
            continue
        baru += 1
        if i % 20 == 0:
            print(f"  ... {i}/{len(perlu)}")

    if gagal:
        print(f"peringatan: {gagal} gambar gagal diunduh")
    return baru, lewat
