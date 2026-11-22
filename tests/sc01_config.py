"""Konfigurasi bersama untuk evaluasi SC-01.

Semua nilai dibaca dari `.env` di akar repo, sehingga tidak perlu mengekspor
variabel manual setiap kali menjalankan test. Variabel lingkungan yang sudah ada
tetap menang, berguna untuk CI atau saat ingin menimpa sementara.

Kunci yang dikenali:

    SC01_SET_UJI      daftar pasangan gambar -> baris (CSV)
    SC01_IMG_DIR      folder gambar bukti transaksi
    GITHUB_TOKEN      dipakai hanya oleh `--siapkan` untuk mengunduh gambar
                      dari repo dataset privat
    GITHUB_DATASET_REPO   default: NafisHandoko/ReworkAcademy
    GITHUB_DATASET_DIR    folder dataset di dalam repo tersebut
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

AKAR = Path(__file__).resolve().parents[1]

# Repo dataset bersifat privat: berisi bukti transaksi perusahaan. Jangan
# dipindahkan ke repo aplikasi yang publik.
REPO_DATASET = os.getenv("GITHUB_DATASET_REPO", "NafisHandoko/ReworkAcademy").strip()
DIR_DATASET = os.getenv(
    "GITHUB_DATASET_DIR",
    "final_project/Dataset PT Lokal Komoditi Indonesia",
).strip()
SUB_DIR_GAMBAR = "Bukti Transaksi Januari 2026"
SUB_DIR_SET_UJI = "sc01/set_uji_1to1.csv"


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


def set_uji() -> Path | None:
    """Lokasi CSV daftar pasangan, atau None bila belum diatur."""
    nilai = os.getenv("SC01_SET_UJI", "").strip()
    return _path(nilai) if nilai else None


def img_dir() -> Path | None:
    """Folder gambar bukti transaksi, atau None bila belum diatur."""
    nilai = os.getenv("SC01_IMG_DIR", "").strip()
    return _path(nilai) if nilai else None


def siap(abaikan_ai: bool = False) -> tuple[bool, str]:
    """Periksa kelengkapan sebelum menjalankan evaluasi.

    Mengembalikan (siap, alasan). Alasan selalu diisi agar pengguna tahu persis
    apa yang kurang, bukan sekadar "skip".
    """
    su = set_uji()
    if su is None:
        return False, "SC01_SET_UJI belum diisi di .env"
    if not su.is_file():
        return False, f"SC01_SET_UJI menunjuk file yang tidak ada: {su}"

    folder = img_dir()
    if folder is None:
        return False, "SC01_IMG_DIR belum diisi di .env"
    if not folder.is_dir():
        return False, f"SC01_IMG_DIR bukan folder: {folder}"

    if not abaikan_ai and not os.getenv("AI_API_KEY", "").strip():
        return False, "AI_API_KEY kosong; SC-01 mengukur model asli, bukan mock"

    with open(su, encoding="utf-8-sig", newline="") as f:
        baris = [r for r in csv.DictReader(f) if (r.get("file") or "").strip()]
    if not baris:
        return False, f"daftar pasangan kosong: {su}"

    hilang = [r["file"].strip() for r in baris
              if not (folder / r["file"].strip()).is_file()]
    if hilang:
        return False, (f"{len(hilang)} dari {len(baris)} gambar tidak ada di {folder}. "
                       f"Jalankan: python3 tests/sc01_harness.py --siapkan")
    return True, f"{len(baris)} pasangan siap diuji"


def baca_pasangan(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if (r.get("file") or "").strip()]


def unduh_gambar(tujuan: Path, token: str | None = None,
                 berkas: list[str] | None = None) -> tuple[int, int]:
    """Unduh gambar dataset dari repo privat. Kembalikan (baru, dilewati).

    Hanya dipakai sekali di awal. Setelah gambar ada di disk, evaluasi berjalan
    sepenuhnya offline terhadap folder itu.
    """
    import urllib.parse
    import urllib.request

    token = (token or os.getenv("GITHUB_TOKEN", "")).strip()
    if not token:
        raise SystemExit(
            "GITHUB_TOKEN kosong. Tambahkan ke .env untuk mengunduh dataset privat."
        )

    su = set_uji()
    if su is None:
        raise SystemExit("SC01_SET_UJI belum diisi; tidak tahu gambar mana yang perlu diunduh")

    perlu = berkas or [r["file"].strip() for r in baca_pasangan(su)]
    tujuan.mkdir(parents=True, exist_ok=True)

    baru = lewat = 0
    for i, nama in enumerate(perlu, 1):
        dst = tujuan / nama
        if dst.is_file() and dst.stat().st_size > 1000:
            lewat += 1
            continue
        jalur = f"{DIR_DATASET}/{SUB_DIR_GAMBAR}/{nama}"
        url = (f"https://api.github.com/repos/{REPO_DATASET}/contents/"
               f"{urllib.parse.quote(jalur)}")
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/vnd.github.raw")
        try:
            data = urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:
            print(f"  GAGAL {nama}: {str(e)[:70]}")
            continue
        dst.write_bytes(data)
        baru += 1
        if i % 20 == 0:
            print(f"  ... {i}/{len(perlu)}")
    return baru, lewat
