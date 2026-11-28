"""SC-06: hasil pencatatan memetakan seluruh kolom wajib cash report.

Kalimat kriteria di BRD menentukan dua hal yang harus diperiksa, dan keduanya
diukur di sini:

1. **susunan kolom** — setiap kolom wajib template perusahaan punya tempat di
   keluaran aplikasi;
2. **hasil pencatatan** — setiap baris yang benar-benar ditulis punya kolom
   wajib terisi.

Bagian 1 saja tidak cukup: susunan kolom bisa lengkap sementara isinya kosong.
Bagian 2 saja juga tidak cukup: satu baris bisa lengkap sementara ada kolom
perusahaan yang tidak punya tempat sama sekali.

Yang **tidak** diukur di sini:

- kebenaran nilai (nominal 20.000 terbaca 50.000 tetap dihitung terisi). Itu
  SC-01 dan SC-02.
- apakah kantong asal dana benar. Nilai bawaan produksi mengisi kolom Kantong
  dengan `CR_DEFAULT_BANK` ketika model gagal membaca, sehingga kolomnya selalu
  terlihat terisi. Kegagalan seperti itu dilaporkan terpisah di
  `docs/bug-kantong-tunai.md`, bukan dijadikan angka kriteria ini.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEMPLATE_FILES = (
    "Cash Report BNI-PT Lokal Komoditi Indonesia 2026.xlsx",
    "Cash Report BRI-PT Lokal Komoditi Indonesia.xlsx",
    "Cash Report Operasional-PT Lokal Komoditi Indonesia 2026.xlsx",
)
TEMPLATE_DIR = "dataset/templates"
DATASET_SUBDIR = "Cash Report dan Mutasi Rekening"
DATASET_REPO = "Project-Rework-G3-AI/rework-ai-finance-assistant-dataset"
HEADER_MARKER = "TANGGAL TRANSAKSI"

# Kolom template yang diisi manusia, bukan data yang bisa dihasilkan bot: bot
# menerima gambar bukti transaksi, bukan identitas admin yang mengunggahnya.
NOT_BOT_DATA = "TANGGAL INPUT DAN NAMA ADMIN"

# Kolom yang dihitung formula di sheet ACCOUNT, bukan ditulis per baris.
DERIVED_COLUMN = "SALDO"

# Kolom yang isinya URL hasil unggah Drive. Diukur terpisah karena butuh Drive
# aktif; harness SC-06 tidak mengaktifkannya, jadi kolom ini dilaporkan
# "tidak diukur" dan dikeluarkan dari penyebut, bukan dianggap gagal.
DRIVE_COLUMN = "LAMPIRAN NOTA"

# Kolom yang berpasangan: satu baris transaksi hanya mengisi salah satunya.
# Menuntut keduanya terisi adalah kesalahan hitung, bukan temuan.
PAIRED_COLUMNS = (
    ("DEBET", "KREDIT"),
    ("KETERANGAN UANG MASUK", "KETERANGAN UANG KELUAR"),
)


# ------------------------------------------------------- bagian 1: susunan kolom


def _cell_text(value) -> str:
    return str(value).strip() if value is not None else ""


@lru_cache(maxsize=16)
def read_company_header(path: Path) -> list[str]:
    """Baca satu baris header template perusahaan.

    Baris header dicari lewat isinya, bukan nomor baris: berkas BNI dan BRI
    menaruhnya di baris 5, berkas Operasional di baris 4.
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
        for row in ws.iter_rows(max_row=12, values_only=True):
            teks = [_cell_text(c) for c in row]
            if any(HEADER_MARKER in t.upper() for t in teks):
                return [t for t in teks if t]
    finally:
        wb.close()
    return []


@lru_cache(maxsize=4)
def read_all_company_headers(directory: Path) -> dict[str, list[str]]:
    """Baca header dari semua berkas template. Kunci: nama berkas."""
    hasil = {}
    for nama in TEMPLATE_FILES:
        path = directory / nama
        if not path.is_file():
            continue
        header = read_company_header(path)
        if header:
            hasil[nama] = header
    return hasil


def read_app_headers() -> list[str]:
    """Kolom yang ditulis aplikasi, diimpor dari kode produksi.

    Diimpor, bukan disalin, supaya kolom baru di produksi tidak lolos tanpa
    diperhatikan.
    """
    sys.path.insert(0, str(ROOT))
    from cash_report.build_template import TRANSAKSI_HEADERS

    return list(TRANSAKSI_HEADERS)


# Setiap kolom wajib perusahaan dipetakan ke kolom aplikasi. Pemetaan ditulis
# eksplisit supaya keputusan "ada" atau "hilang" bisa diperiksa orang lain,
# bukan hasil tebakan pencocokan nama.
MAPPING: dict[str, tuple[str, str, str]] = {
    NOT_BOT_DATA: ("not_bot_data", "",
                   "Diisi manusia di template; bot tidak menerima identitas admin"),
    "TANGGAL TRANSAKSI": ("direct", "A", ""),
    "KETERANGAN": ("direct", "F", ""),
    "KATEGORI": ("direct", "E", ""),
    # Isi kedua kolom ini di template perusahaan adalah NAMA KANTONG, bukan teks
    # bebas. Aplikasi menuliskannya lewat kolom Kantong (B) dengan memecah
    # transfer menjadi dua baris.
    "KETERANGAN UANG MASUK": ("split", "B",
                              "Kantong pada baris masuk (transfer dipecah dua baris)"),
    "KETERANGAN UANG KELUAR": ("split", "B",
                               "Kantong pada baris keluar (transfer dipecah dua baris)"),
    "DEBET": ("direct", "C", "Masuk"),
    "KREDIT": ("direct", "D", "Keluar"),
    DERIVED_COLUMN: ("derived", "ACCOUNT!E", "Saldo Akhir per kantong dihitung formula"),
    DRIVE_COLUMN: ("direct", "K", "Link Bukti"),
}

# Kolom yang hidup di sheet lain, bukan di TRANSAKSI.
OTHER_SHEET_COLUMNS = {"ACCOUNT!E": "Saldo Akhir per kantong (formula di sheet ACCOUNT)"}

LABEL = {
    "direct": "langsung",
    "derived": "diturunkan",
    "split": "terbagi",
    "not_bot_data": "bukan data bot",
    "missing": "HILANG",
}


def _column_exists(app_col: str, app: list[str]) -> bool:
    """Apakah kolom yang diklaim benar-benar ada di keluaran aplikasi."""
    if app_col in OTHER_SHEET_COLUMNS:
        return True
    sheet, _, col = app_col.partition("!")
    if sheet and col:
        return False
    if not sheet.isalpha():
        return False
    return sheet in [chr(ord("A") + j) for j in range(len(app))]


@dataclass
class ColumnScore:
    letter: str
    title: str
    mapping: str
    app_column: str
    note: str


def score_columns(company: list[str], app: list[str]) -> list[ColumnScore]:
    """Nilai setiap kolom wajib perusahaan terhadap kolom aplikasi."""
    hasil = []
    for i, title in enumerate(company):
        letter = chr(ord("A") + i)
        jenis, app_col, note = MAPPING.get(title, ("missing", "", "belum dipetakan"))
        if jenis != "missing" and app_col and not _column_exists(app_col, app):
            jenis = "missing"
            note = f"kolom {app_col} tidak ada di keluaran aplikasi"
        hasil.append(ColumnScore(letter, title, jenis, app_col, note))
    return hasil


# --------------------------------------------- bagian 2: kelengkapan per baris


def written_rows(raw: dict) -> list[list]:
    """Baris sheet yang akan ditulis produksi dari satu balasan model.

    Meniru `main.write_cash_report` (main.py:425-472). Tiruan ini dijaga test
    yang membandingkannya dengan produksi, karena kalau keduanya berbeda maka
    angka SC-06 mengukur tiruan, bukan aplikasi.
    """
    import main

    kantong = str(raw.get("bank") or "").strip().upper() or main.CR_DEFAULT_BANK
    tujuan = str(raw.get("kantong_tujuan") or "").strip().upper()
    arah = raw.get("arah")
    nominal = raw.get("nominal") or 0
    is_pair = bool(arah == "transfer" and tujuan and tujuan != kantong)
    masuk = arah == "masuk"

    def _baris(k_: str, keluar, masuk_nilai) -> list:
        # Kategori dinilai kosong bila `normalize` mengembalikan penanda
        # PERLU_DITINJAU. Fungsi itu tidak pernah mengembalikan None, jadi tanpa
        # pemeriksaan ini kategori yang gagal dibaca akan terlihat terisi.
        kategori = main.KAT.normalize(raw.get("kategori"))
        if kategori == main.KAT.PERLU_DITINJAU:
            kategori = ""
        return ["2026-01-01 00:00:00", k_, masuk_nilai, keluar,
                kategori,
                str(raw.get("keterangan") or ""), "draft", "",
                "tg:tiruan", str(raw.get("sumber_file") or ""), ""]

    if is_pair:
        return [_baris(kantong, nominal, ""), _baris(tujuan, "", nominal)]
    return [_baris(kantong, "" if masuk else nominal, nominal if masuk else "")]


def row_as_columns(baris: list, drive_enabled: bool = False) -> dict[str, str]:
    """Petakan satu baris sheet (A-K) ke nama kolom template perusahaan."""
    tanggal, kantong, masuk, keluar, kategori, keterangan = baris[0], baris[1], baris[2], baris[3], baris[4], baris[5]
    link = baris[10]
    return {
        "TANGGAL TRANSAKSI": str(tanggal or ""),
        "KETERANGAN": str(keterangan or ""),
        "KATEGORI": str(kategori or ""),
        "KETERANGAN UANG MASUK": kantong if str(masuk or "").strip() else "",
        "KETERANGAN UANG KELUAR": kantong if str(keluar or "").strip() else "",
        "DEBET": masuk,
        "KREDIT": keluar,
        DERIVED_COLUMN: "diturunkan",
        DRIVE_COLUMN: str(link or "") if drive_enabled else "tidak diukur",
    }


@dataclass
class RowScore:
    file: str
    nomor: int
    missing: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing


def score_row(baris: list, file: str, nomor: int, drive_enabled: bool = False) -> RowScore:
    """Nilai satu baris: kolom wajib mana yang kosong."""
    kolom = row_as_columns(baris, drive_enabled)
    kurang = []
    for judul, (jenis, _, _) in MAPPING.items():
        if jenis == "not_bot_data":
            continue
        if jenis == "derived":
            continue
        if judul == DRIVE_COLUMN and not drive_enabled:
            continue
        if judul in [c for par in PAIRED_COLUMNS for c in par]:
            continue
        if not str(kolom.get(judul) or "").strip():
            kurang.append(judul)

    for a, b in PAIRED_COLUMNS:
        if not str(kolom.get(a) or "").strip() and not str(kolom.get(b) or "").strip():
            kurang.append(f"{a} & {b}")

    return RowScore(file=file, nomor=nomor, missing=kurang)


# --------------------------------------------------------------- agregasi


@dataclass
class Report:
    columns: list[ColumnScore] = field(default_factory=list)
    rows: list[RowScore] = field(default_factory=list)
    template_files: list[str] = field(default_factory=list)
    app_headers: list[str] = field(default_factory=list)
    failed_images: int = 0
    drive_enabled: bool = False

    @property
    def bot_relevant(self) -> list[ColumnScore]:
        return [c for c in self.columns if c.mapping != "not_bot_data"]

    @property
    def missing_columns(self) -> list[ColumnScore]:
        return [c for c in self.bot_relevant if c.mapping == "missing"]

    @property
    def total_rows(self) -> int:
        return len(self.rows)

    @property
    def complete_rows(self) -> int:
        return sum(1 for r in self.rows if r.complete)

    @property
    def row_rate(self) -> float:
        return (self.complete_rows / self.total_rows * 100.0) if self.total_rows else 0.0

    @property
    def measured(self) -> bool:
        return bool(self.columns) and self.total_rows > 0 and not self.failed_images

    @property
    def pass_verdict(self) -> bool:
        # Dua bagian, keduanya wajib: tidak ada kolom hilang, dan tidak ada baris
        # yang kehilangan kolom wajib.
        return (not self.missing_columns
                and self.total_rows > 0
                and self.complete_rows == self.total_rows)


def compute(rows: list[dict], template_dir: Path | None = None,
            drive_enabled: bool = False) -> Report:
    """Hitung SC-06 dari template perusahaan dan balasan model.

    `rows` berisi dict dengan kunci `file`, `raw` (balasan model), dan `error`.
    """
    directory = template_dir or (ROOT / TEMPLATE_DIR)
    headers = read_all_company_headers(directory)
    if not headers:
        raise FileNotFoundError(
            f"template perusahaan tidak ditemukan di {directory}")

    # Semua berkas harus sepakat soal kolom wajib. Bila berbeda, dipakai irisan
    # tersempit supaya tidak ada kolom yang lolos tanpa bukti.
    daftar = list(headers.values())
    wajib = [t for t in daftar[0] if all(t in d for d in daftar[1:])]

    app = read_app_headers()
    laporan = Report(
        columns=score_columns(wajib, app),
        template_files=sorted(headers),
        app_headers=app,
        drive_enabled=drive_enabled,
    )

    for row in rows:
        nama = str(row.get("file") or "")
        if str(row.get("error") or "").strip():
            laporan.failed_images += 1
            continue
        raw = row.get("raw") or {}
        for i, baris in enumerate(written_rows(raw), 1):
            laporan.rows.append(score_row(baris, nama, i, drive_enabled))

    return laporan


def verdict(report: Report) -> str:
    if not report.columns:
        return "BELUM DIUKUR"
    if not report.total_rows:
        return "BELUM DIUKUR"
    if report.failed_images:
        return "GAGAL DIUKUR"
    return "TERCAPAI" if report.pass_verdict else "BELUM TERCAPAI"


# ------------------------------------------------------------------- laporan


def write_report(report: Report, out_dir: Path) -> tuple[Path, Path]:
    """Tulis laporan teks dan CSV. Kembalikan (teks, csv)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    txt = out_dir / "sc06_report.txt"
    csv_path = out_dir / "sc06_rows.csv"

    baris = [
        "SC-06: hasil pencatatan memetakan seluruh kolom wajib cash report",
        "=" * 68,
        "",
        "Target (BRD): tidak ada kolom wajib yang hilang",
        "Cara periksa (BRD): membandingkan susunan kolom keluaran dengan kolom",
        "                    wajib pada template cash report perusahaan",
        "",
        f"Template perusahaan dibaca : {len(report.template_files)} berkas",
    ]
    for nama in report.template_files:
        baris.append(f"  - {nama}")

    baris += [
        "",
        "BAGIAN 1 - SUSUNAN KOLOM",
        "-" * 68,
        f"{'#':<3} {'Kolom perusahaan':<32} {'Nasib':<15} {'Kolom app':<10}",
        "-" * 68,
    ]
    for c in report.columns:
        baris.append(f"{c.letter:<3} {c.title[:31]:<32} "
                     f"{LABEL.get(c.mapping, c.mapping):<15} {c.app_column:<10}")

    baris += [
        "",
        f"Kolom relevan bot : {len(report.bot_relevant)}",
        f"Kolom hilang      : {len(report.missing_columns)}",
    ]
    for c in report.missing_columns:
        baris.append(f"  HILANG: {c.title} — {c.note}")

    baris += [
        "",
        "BAGIAN 2 - KELENGKAPAN HASIL PENCATATAN",
        "-" * 68,
        f"Baris ditulis     : {report.total_rows}",
        f"Baris lengkap     : {report.complete_rows}",
        f"Baris kurang      : {report.total_rows - report.complete_rows}",
    ]
    if report.failed_images:
        baris.append(f"Gambar gagal dipanggil: {report.failed_images}")

    kurang = [r for r in report.rows if not r.complete]
    if kurang:
        baris += ["", "Baris yang kehilangan kolom wajib", "-" * 68]
        for r in kurang[:40]:
            baris.append(f"  {r.file} (baris {r.nomor}): {', '.join(r.missing)}")
        if len(kurang) > 40:
            baris.append(f"  ... dan {len(kurang) - 40} baris lain")

    if not report.drive_enabled:
        baris += [
            "",
            "Catatan: kolom LAMPIRAN NOTA tidak diukur di harness ini karena",
            "isinya URL hasil unggah Drive. Kolom itu dikeluarkan dari penyebut,",
            "bukan dianggap gagal.",
        ]

    baris += [
        "",
        f"Angka yang dinilai : {report.complete_rows} dari {report.total_rows} baris "
        "lengkap  <- dibandingkan dengan target",
        f"Status             : {verdict(report)}",
    ]

    txt.write_text("\n".join(baris) + "\n", encoding="utf-8")

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "baris", "lengkap", "kolom_kurang"])
        for r in report.rows:
            w.writerow([r.file, r.nomor, "ya" if r.complete else "tidak",
                        "|".join(r.missing)])
    return txt, csv_path


def download_templates(target_dir: Path) -> list[Path]:
    """Unduh template perusahaan dari repo dataset.

    Butuh `GITHUB_TOKEN` bila repo privat. Tanpa token, `raw.githubusercontent`
    tetap bisa dipakai untuk repo publik.
    """
    import os
    import urllib.parse
    import urllib.request

    target_dir.mkdir(parents=True, exist_ok=True)
    token = os.getenv("GITHUB_TOKEN", "").strip()
    hasil = []
    for name in TEMPLATE_FILES:
        quoted = urllib.parse.quote(name)
        subdir = urllib.parse.quote(DATASET_SUBDIR)
        url = (f"https://raw.githubusercontent.com/{DATASET_REPO}/main/"
               f"{subdir}/{quoted}")
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        dest = target_dir / name
        with urllib.request.urlopen(req, timeout=60) as resp:
            dest.write_bytes(resp.read())
        hasil.append(dest)
    return hasil
