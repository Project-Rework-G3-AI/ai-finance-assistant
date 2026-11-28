"""Konfigurasi bersama untuk seluruh suite kriteria (SC-01 sampai SC-08).

Modul ini sengaja tidak menyebut satu kriteria pun di namanya, karena daftar
pasangan dan folder gambar dipakai bersama: `file` menentukan foto yang diproses
SC-01, SC-02, SC-03, SC-04, dan SC-06; `kategori_acuan` menjadi jawaban benar
untuk SC-01; sedangkan `tanggal`, `nominal_acuan`, `bank`, dan
`keterangan_gambar` menjadi acuan kelengkapan untuk SC-02.

Semua nilai dibaca dari `.env` di akar repo, sehingga tidak perlu mengekspor
variabel manual setiap kali menjalankan test. Variabel lingkungan yang sudah ada
tetap menang, berguna untuk CI atau saat ingin menimpa sementara.

Kunci yang dikenali:

    SC_PAIRS            daftar pasangan gambar -> baris (CSV)
    SC_IMAGES           folder gambar bukti transaksi
    GITHUB_TOKEN          opsional; hanya dipakai bila repo dataset privat
    GITHUB_DATASET_REPO   default: Project-Rework-G3-AI/rework-ai-finance-assistant-dataset
    GITHUB_DATASET_DIR    folder dataset di dalam repo tersebut
    GITHUB_DATASET_BRANCH branch repo dataset, default: main

Kedua kunci SC_* punya nilai bawaan yang masuk akal, jadi `.env` baru dari
`.env.example` sudah bisa dipakai tanpa disunting lebih dulu.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Repo dataset berisi bukti transaksi perusahaan. Jangan pakai repo pribadi
# seseorang — semua anggota kelompok harus bisa mengaksesnya.
DATASET_REPO = os.getenv(
    "GITHUB_DATASET_REPO", "Project-Rework-G3-AI/rework-ai-finance-assistant-dataset"
).strip()
# Folder dataset di dalam repo tersebut. Kosong berarti berkas ada di akar repo.
DATASET_DIR = os.getenv("GITHUB_DATASET_DIR", "").strip()
DATASET_BRANCH = os.getenv("GITHUB_DATASET_BRANCH", "main").strip()
IMAGES_SUBDIR = "Bukti Transaksi Januari 2026"
PAIRS_SUBDIR = "pairs.csv"

# PDF mutasi rekening untuk SC-07. Repo dataset memakai spasi pada nama berkas;
# nama lokal memakai garis bawah supaya bisa dipakai di perintah shell tanpa
# tanda kutip. Pemetaan ini satu-satunya tempat kedua nama itu ditulis.
STATEMENTS_SUBDIR = "Cash Report dan Mutasi Rekening"
STATEMENT_FILES = {
    "BNI_Mutasi_Januari_2026.pdf": "BNI_Mutasi_Januari_2026.pdf",
    "Mutasi_Rekening_BRI-Januari_2026.pdf": "Mutasi Rekening BRI-Januari 2026.pdf",
}

# Kunci balikan `main.extract` memakai bahasa Indonesia karena fungsi itu dipakai
# jalur produksi (Telegram, Sheets) yang sudah berjalan. Dipetakan di sini supaya
# harness memakai nama Inggris tanpa mengubah kontrak produksi.
EXTRACT_KEYS = {
    "kategori": "category",
    "nominal": "amount",
    "tanggal": "date",
    "mode": "mode",
    "keterangan": "note",
    "catatan": "remark",
    "bank": "bank",
    "arah": "direction",
    "kantong_tujuan": "target_wallet",
}


def normalize_extract(rec: dict) -> dict:
    """Petakan balikan `main.extract` ke kunci Inggris."""
    out = {}
    for k, v in (rec or {}).items():
        out[EXTRACT_KEYS.get(k, k)] = v
    return out


# Nilai bawaan: mengikuti susunan folder yang dibuat `--download`.
DEFAULT_PAIRS = "dataset/pairs.csv"
DEFAULT_IMAGES = "dataset/Bukti Transaksi Januari 2026"


def load_env() -> None:
    """Muat `.env` di akar repo tanpa menimpa variabel yang sudah ada."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dotenv sudah jadi dependensi
        return
    load_dotenv(ROOT / ".env", override=False)


def _resolve(value: str) -> Path:
    p = Path(value).expanduser()
    return p if p.is_absolute() else (ROOT / p).resolve()


def pairs_file() -> Path:
    """Lokasi CSV daftar pasangan. Kembalikan nilai bawaan bila belum diatur."""
    value = os.getenv("SC_PAIRS", "").strip() or DEFAULT_PAIRS
    return _resolve(value)


def images_dir() -> Path:
    """Folder gambar bukti transaksi. Kembalikan nilai bawaan bila belum diatur."""
    value = os.getenv("SC_IMAGES", "").strip() or DEFAULT_IMAGES
    return _resolve(value)


# Nama kolom pada CSV dataset memakai bahasa Indonesia karena berkas itu sudah
# ada lebih dulu dan dipakai bersama. Dipetakan sekali di sini agar sisa kode
# memakai nama Inggris, tanpa perlu mengubah berkas datanya.
PAIR_COLUMNS = {
    "file": "file",
    "kategori_acuan": "reference_category",
    "nominal_acuan": "reference_amount",
    "tanggal": "reference_date",
    "nominal_gambar": "image_amount",
    "keterangan_gambar": "image_note",
    "kategori_acuan_asli": "reference_category_raw",
    "sumber_acuan": "reference_source",
    "baris_xlsx": "source_row",
}


def read_pairs(path: Path) -> list[dict]:
    """Baca daftar pasangan. Beri pesan jelas bila berkasnya belum ada.

    Kunci hasil dipetakan ke nama Inggris; kolom yang tidak dikenal dibiarkan
    apa adanya supaya penambahan kolom baru di dataset tidak memecahkan kode.
    """
    if not Path(path).is_file():
        raise SystemExit(
            f"daftar pasangan belum ada: {path}\n"
            "Jalankan lebih dulu: python3 tests/sc_runner.py --download"
        )
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = []
        for raw in csv.DictReader(f):
            if not (raw.get("file") or "").strip():
                continue
            row = {PAIR_COLUMNS.get(k, k): v for k, v in raw.items()}
            rows.append(row)
        return rows


def ready(skip_ai_check: bool = False) -> tuple[bool, str]:
    """Periksa kelengkapan sebelum menjalankan evaluasi.

    Mengembalikan (siap, alasan). Alasan selalu diisi agar pengguna tahu persis
    apa yang kurang, bukan sekadar "skip".
    """
    pairs_path = pairs_file()
    if not pairs_path.is_file():
        return False, (f"daftar pasangan belum ada: {pairs_path}. "
                       f"Jalankan: python3 tests/sc_runner.py --download")

    folder = images_dir()
    if not folder.is_dir():
        return False, (f"folder gambar belum ada: {folder}. "
                       f"Jalankan: python3 tests/sc_runner.py --download")

    if not skip_ai_check and not os.getenv("AI_API_KEY", "").strip():
        return False, "AI_API_KEY kosong; SC-01 mengukur model asli, bukan mock"

    rows = read_pairs(pairs_path)
    if not rows:
        return False, f"daftar pasangan kosong: {pairs_path}"

    missing = [r["file"].strip() for r in rows
               if not (folder / r["file"].strip()).is_file()]
    if missing:
        return False, (f"{len(missing)} dari {len(rows)} gambar tidak ada di {folder}. "
                       f"Jalankan: python3 tests/sc_runner.py --download")
    return True, f"{len(rows)} pasangan siap diuji"


def _token(value: str | None = None) -> str | None:
    """Token GitHub, bila ada. Repo dataset publik, jadi token tidak wajib.

    Dibiarkan opsional supaya anggota tidak perlu membuat token hanya untuk
    mengunduh data. Bila nanti repo dijadikan privat lagi, token tetap dipakai
    secara otomatis tanpa perubahan kode.
    """
    return (value or os.getenv("GITHUB_TOKEN", "")).strip() or None


def _fetch_file(repo_path: str) -> bytes:
    """Ambil berkas, mencoba akses anonim lalu memakai token bila perlu.

    Repo dataset semestinya publik, jadi akses anonim biasanya cukup dan tidak
    memerlukan token. Bila repo ternyata privat, percobaan anonim menghasilkan
    404; token yang tersedia di .env dipakai supaya pengguna tidak perlu tahu
    detail itu.
    """
    token = _token()
    if token:
        try:
            return _fetch_from_github(repo_path, None)
        except SystemExit:
            return _fetch_from_github(repo_path, token)
    return _fetch_from_github(repo_path, None)


def _repo_path(*parts: str) -> str:
    """Rangkai jalur di dalam repo dataset, tanpa garis miring berlebih."""
    segments = [DATASET_DIR] if DATASET_DIR else []
    segments.extend(parts)
    return "/".join(p.strip("/") for p in segments if p.strip("/"))


def _fetch_from_github(repo_path: str, token: str | None = None) -> bytes:
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
        url = (f"https://raw.githubusercontent.com/{DATASET_REPO}/"
               f"{DATASET_BRANCH}/{urllib.parse.quote(repo_path)}")
        source = "raw.githubusercontent.com (tanpa token)"
    else:
        url = (f"https://api.github.com/repos/{DATASET_REPO}/contents/"
               f"{urllib.parse.quote(repo_path)}")
        source = "API GitHub (dengan token)"

    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Accept", "application/vnd.github.raw")

    try:
        return urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise SystemExit(
                f"berkas tidak ditemukan: {repo_path}\n"
                f"  sumber : {source}\n"
                f"  repo   : {DATASET_REPO} (branch {DATASET_BRANCH})\n"
                "Kemungkinan penyebab:\n"
                "  1. Repo dataset sedang privat, sehingga akses tanpa token ditolak.\n"
                "     Isi GITHUB_TOKEN di .env, atau minta pemilik repo menjadikannya publik.\n"
                "  2. Nama repo atau branch berubah. Periksa GITHUB_DATASET_REPO\n"
                "     dan GITHUB_DATASET_BRANCH di .env."
            ) from None
        if e.code in (403, 429):
            raise SystemExit(
                f"akses ditolak atau kena batas kuota: HTTP {e.code}\n"
                f"  sumber : {source}\n"
                "Isi GITHUB_TOKEN di .env untuk memakai kuota akunmu sendiri."
            ) from None
        raise SystemExit(f"gagal mengunduh {repo_path}: HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise SystemExit(
            f"tidak bisa menghubungi GitHub: {e.reason}\n"
            "Periksa koneksi internet, lalu jalankan ulang perintah yang sama."
        ) from None


def statements_dir() -> Path:
    """Folder tempat PDF mutasi rekening disimpan."""
    return Path(os.getenv("SC07_STATEMENT_DIR", "dataset/mutasi"))


def download_pairs(target: Path | None = None,
                   token: str | None = None) -> Path:
    """Unduh daftar pasangan dari repo dataset bila belum ada.

    `--download` butuh daftar pasangan untuk tahu gambar mana yang harus diambil,
    sedangkan daftar itu sendiri juga ada di repo yang sama. Fungsi ini memutus
    ketergantungan tersebut sehingga satu perintah cukup.
    """
    target = target or pairs_file()
    if target.is_file() and target.stat().st_size > 100:
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"mengunduh daftar pasangan ke: {target}")
    target.write_bytes(_fetch_file(_repo_path(PAIRS_SUBDIR)))
    return target


def download_statements(target: Path | None = None,
                        token: str | None = None) -> list[Path]:
    """Unduh PDF mutasi rekening dari repo dataset bila belum ada.

    Nama berkas di repo dataset memakai spasi, sedangkan SC-07 menyimpannya
    dengan garis bawah. Pemetaan itu ditulis di sini supaya orang lain tidak
    perlu menyalin berkas dengan nama yang tepat secara manual.
    """
    target = target or statements_dir()
    target.mkdir(parents=True, exist_ok=True)

    hasil = []
    for nama_lokal, nama_repo in STATEMENT_FILES.items():
        local = target / nama_lokal
        if local.is_file() and local.stat().st_size > 1000:
            hasil.append(local)
            continue
        print(f"mengunduh {nama_repo} -> {local.name}")
        local.write_bytes(_fetch_file(_repo_path(STATEMENTS_SUBDIR, nama_repo)))
        hasil.append(local)
    return hasil


def download_images(target: Path | None = None, token: str | None = None,
                    filenames: list[str] | None = None) -> tuple[int, int]:
    """Unduh gambar dataset dari repo. Kembalikan (baru, dilewati).

    Hanya dipakai sekali di awal. Setelah gambar ada di disk, evaluasi berjalan
    sepenuhnya offline terhadap folder itu.

    Galat dicatat lalu dilanjutkan, supaya satu berkas bermasalah tidak
    membatalkan seluruh unduhan. Ringkasannya dilaporkan di akhir.
    """
    target = target or images_dir()

    needed = filenames or [r["file"].strip() for r in read_pairs(pairs_file())]
    target.mkdir(parents=True, exist_ok=True)

    downloaded = skipped = failed = 0
    error_message = ""
    for i, name in enumerate(needed, 1):
        etc_items = target / name
        if etc_items.is_file() and etc_items.stat().st_size > 1000:
            skipped += 1
            continue
        try:
            etc_items.write_bytes(_fetch_file(_repo_path(IMAGES_SUBDIR, name)))
        except SystemExit as e:
            # Pesan sudah informatif; simpan sekali, jangan cetak 65 kali.
            error_message = error_message or str(e)
            failed += 1
            continue
        except Exception as e:
            error_message = error_message or f"{type(e).__name__}: {e}"
            failed += 1
            continue
        downloaded += 1
        if i % 20 == 0:
            print(f"  ... {i}/{len(needed)}")

    if failed:
        print(f"peringatan: {failed} dari {len(needed)} gambar gagal diunduh")
        if error_message:
            print("  " + error_message.replace("\n", "\n  "))
    return downloaded, skipped
