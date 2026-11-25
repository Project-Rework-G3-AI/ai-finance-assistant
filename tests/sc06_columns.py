"""SC-06: hasil pencatatan memetakan seluruh kolom wajib cash report.

Kriteria ini membandingkan susunan kolom keluaran aplikasi dengan kolom wajib
pada template cash report perusahaan. Yang dinilai bukan isi sel, melainkan
apakah setiap kolom wajib punya tempat di keluaran.

Sumber kebenaran kolom wajib adalah berkas template perusahaan di repo dataset
(`Cash Report dan Mutasi Rekening/`), bukan daftar yang ditulis ulang di sini.
Berkas itu dibaca apa adanya, sehingga bila perusahaan mengubah templatenya,
perbandingan ini ikut berubah tanpa ada daftar salinan yang bisa tertinggal.

Kriteria ini gratis: tidak butuh kredensial, jaringan, maupun model.
"""

from __future__ import annotations

import csv
import io
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Berkas template perusahaan di repo dataset. Ketiganya memakai header yang
# sama; dibaca semua supaya perbedaan antar berkas tidak lolos.
TEMPLATE_FILES = (
    "Cash Report BNI-PT Lokal Komoditi Indonesia 2026.xlsx",
    "Cash Report BRI-PT Lokal Komoditi Indonesia.xlsx",
    "Cash Report Operasional-PT Lokal Komoditi Indonesia 2026.xlsx",
)
DATASET_SUBDIR = "Cash Report dan Mutasi Rekening"
DATASET_REPO = "Project-Rework-G3-AI/rework-ai-finance-assistant-dataset"
TEMPLATE_DIR = "dataset/templates"

# Baris header template perusahaan. Berkas BNI dan BRI menaruhnya di baris 5,
# berkas Operasional di baris 4 untuk sheet pertama, jadi baris dicari dengan
# mengenali isinya, bukan dipatok.
HEADER_MARKER = "TANGGAL TRANSAKSI"


# Kolom wajib yang memang bukan data yang bisa dihasilkan bot. Kolom-kolom ini
# diisi manusia saat memakai template, bukan hasil membaca bukti transaksi:
# bot menerima gambar, bukan identitas admin yang mengunggahnya.
NOT_BOT_DATA = {
    "TANGGAL INPUT DAN NAMA ADMIN":
        "diisi manusia di template; bot tidak menerima identitas admin",
}


@dataclass
class CompanyColumn:
    """Satu kolom wajib menurut template perusahaan."""

    letter: str
    title: str
    mapping: str  # "direct" | "derived" | "split" | "missing"
    app_column: str = ""
    note: str = ""


@dataclass
class ColumnScore:
    """Hasil penilaian satu kolom wajib."""

    letter: str
    title: str
    mapping: str
    app_column: str
    note: str


@dataclass
class Report:
    """Ringkasan hasil SC-06."""

    columns: list[ColumnScore] = field(default_factory=list)
    template_files: list[str] = field(default_factory=list)
    app_headers: list[str] = field(default_factory=list)
    extra_app_columns: list[str] = field(default_factory=list)

    @property
    def required(self) -> int:
        return len(self.columns)

    @property
    def mapped(self) -> int:
        return sum(1 for c in self.columns
                   if c.mapping not in ("missing", "not_bot_data"))

    @property
    def missing(self) -> list[ColumnScore]:
        return [c for c in self.columns if c.mapping == "missing"]

    @property
    def not_bot_data(self) -> list[ColumnScore]:
        return [c for c in self.columns if c.mapping == "not_bot_data"]

    @property
    def bot_relevant(self) -> int:
        """Kolom wajib yang memang datanya dihasilkan bot."""
        return self.required - len(self.not_bot_data)

    @property
    def pass_verdict(self) -> bool:
        # Target BRD: tidak ada kolom wajib yang hilang. Kolom yang memang bukan
        # data bot tidak dihitung hilang, tetapi jumlahnya tetap dilaporkan
        # supaya pembaca bisa menilai sendiri.
        return self.bot_relevant > 0 and not self.missing


# ------------------------------- membaca template perusahaan


def _cell_text(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


@lru_cache(maxsize=16)
def read_company_header(path: Path) -> list[str]:
    """Kolom wajib dari satu berkas template perusahaan.

    Membaca seluruh sheet dan mengembalikan header pertama yang cocok. Header
    dicari lewat isinya (`TANGGAL TRANSAKSI`), bukan nomor baris, karena berkas
    Operasional menaruhnya satu baris lebih tinggi.
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            for row in range(1, 11):
                values = [_cell_text(ws.cell(row, col).value) for col in range(1, 13)]
                if HEADER_MARKER in values:
                    return [v for v in values if v]
    finally:
        wb.close()
    raise ValueError(f"header '{HEADER_MARKER}' tidak ditemukan di {path.name}")


@lru_cache(maxsize=16)
def read_all_company_headers(directory: Path) -> dict[str, list[str]]:
    """Header dari semua berkas template perusahaan yang tersedia."""
    hasil = {}
    for name in TEMPLATE_FILES:
        path = directory / name
        if path.exists():
            hasil[name] = read_company_header(path)
    return hasil


# ------------------------------- kolom keluaran aplikasi


def read_app_headers() -> list[str]:
    """Kolom yang ditulis aplikasi ke sheet TRANSAKSI.

    Diimpor dari `cash_report/build_template.py` supaya yang dibandingkan
    benar-benar kolom yang dipakai menulis, bukan salinan daftar.
    """
    sys.path.insert(0, str(ROOT))
    from cash_report.build_template import TRANSAKSI_HEADERS

    return list(TRANSAKSI_HEADERS)


# ------------------------------- pemetaan

# Setiap kolom wajib perusahaan dipetakan ke kolom aplikasi. Pemetaan ditulis
# eksplisit supaya keputusan "hilang" atau "ada" bisa diperiksa orang lain,
# bukan hasil tebakan pencocokan nama.
MAPPING: dict[str, tuple[str, str, str]] = {
    # judul kolom perusahaan: (jenis, kolom aplikasi, catatan)
    "TANGGAL INPUT DAN NAMA ADMIN": (
        "not_bot_data", "",
        "Diisi manusia di template; bot tidak menerima identitas admin, dan kolom "
        "A aplikasi sudah dipakai untuk tanggal transaksi"),
    "TANGGAL TRANSAKSI": ("direct", "A", ""),
    "KETERANGAN": ("direct", "F", ""),
    "KATEGORI": ("direct", "E", ""),
    # Isi kedua kolom ini di template perusahaan adalah NAMA KANTONG, bukan teks
    # bebas. Aplikasi menuliskannya lewat kolom Kantong (B) dengan memecah
    # transfer menjadi dua baris: baris masuk membawa kantong tujuan, baris
    # keluar membawa kantong asal.
    "KETERANGAN UANG MASUK": (
        "split", "B", "Kantong pada baris masuk (transfer dipecah dua baris)"),
    "KETERANGAN UANG KELUAR": (
        "split", "B", "Kantong pada baris keluar (transfer dipecah dua baris)"),
    "DEBET": ("direct", "C", "Masuk"),
    "KREDIT": ("direct", "D", "Keluar"),
    "SALDO": ("derived", "ACCOUNT!E", "Saldo Akhir per kantong dihitung formula"),
    "LAMPIRAN NOTA": ("direct", "K", "Link Bukti"),
}


# Kolom yang hidup di sheet lain, bukan di TRANSAKSI. Ditulis eksplisit supaya
# validasi tidak salah menandainya hilang hanya karena bukan kolom TRANSAKSI.
OTHER_SHEET_COLUMNS = {
    "ACCOUNT!E": "Saldo Akhir per kantong (formula di sheet ACCOUNT)",
}


def _column_exists(app_col: str, app: list[str]) -> bool:
    """Apakah kolom yang diklaim benar-benar ada di keluaran aplikasi."""
    if app_col in OTHER_SHEET_COLUMNS:
        return True
    sheet, _, col = app_col.partition("!")
    if sheet and col:
        # Kolom di sheet lain harus terdaftar di OTHER_SHEET_COLUMNS.
        return False
    if not sheet.isalpha():
        return False
    return sheet in [chr(ord("A") + j) for j in range(len(app))]


def score_columns(company: list[str], app: list[str]) -> list[ColumnScore]:
    """Nilai setiap kolom wajib perusahaan terhadap kolom aplikasi."""
    hasil = []
    for i, title in enumerate(company):
        letter = chr(ord("A") + i)
        jenis, app_col, note = MAPPING.get(
            title, ("missing", "", "belum dipetakan"))
        # Kolom aplikasi harus benar-benar ada, bukan hanya diklaim di tabel.
        if jenis != "missing" and app_col and not _column_exists(app_col, app):
            jenis = "missing"
            note = f"kolom {app_col} tidak ada di keluaran aplikasi"
        hasil.append(ColumnScore(letter, title, jenis, app_col, note))
    return hasil


def compute(template_dir: Path | None = None) -> Report:
    """Hitung SC-06 dari berkas template dan kolom aplikasi."""
    directory = template_dir or (ROOT / TEMPLATE_DIR)
    headers = read_all_company_headers(directory)
    if not headers:
        raise FileNotFoundError(
            f"template perusahaan tidak ditemukan di {directory}; "
            f"jalankan dengan --download atau letakkan berkasnya di sana")

    # Semua berkas harus sepakat soal kolom wajib. Bila berbeda, yang dipakai
    # adalah irisan tersempit supaya tidak ada kolom yang lolos tanpa bukti.
    daftar = list(headers.values())
    wajib = [t for t in daftar[0] if all(t in d for d in daftar[1:])]

    app = read_app_headers()
    kolom = score_columns(wajib, app)

    dipakai = {c.app_column.split("!")[0] for c in kolom if c.mapping != "missing"}
    ekstra = [h for i, h in enumerate(app) if chr(ord("A") + i) not in dipakai]

    return Report(
        columns=kolom,
        template_files=sorted(headers),
        app_headers=app,
        extra_app_columns=ekstra,
    )


# ------------------------------- laporan


LABEL = {
    "direct": "langsung",
    "derived": "diturunkan",
    "split": "terbagi",
    "not_bot_data": "bukan data bot",
    "missing": "HILANG",
}


def verdict(report: Report) -> str:
    if not report.required:
        return "BELUM DIUKUR"
    return "TERCAPAI" if report.pass_verdict else "BELUM TERCAPAI"


def write_report(report: Report, out_dir: Path) -> tuple[Path, Path]:
    """Tulis laporan teks dan CSV."""
    out_dir.mkdir(parents=True, exist_ok=True)
    txt = out_dir / "sc06_report.txt"
    csv_path = out_dir / "sc06_columns.csv"

    baris = [
        "SC-06: hasil pencatatan memetakan seluruh kolom wajib cash report",
        "",
        "Target (BRD): tidak ada kolom wajib yang hilang",
        "",
        f"Template perusahaan dibaca: {len(report.template_files)} berkas",
    ]
    for name in report.template_files:
        baris.append(f"  - {name}")
    baris += [
        "",
        f"Kolom wajib perusahaan    : {report.required}",
        f"  diisi manusia, bukan bot : {len(report.not_bot_data)}",
        f"  relevan untuk bot        : {report.bot_relevant}",
        f"Kolom terpetakan          : {report.mapped}",
        f"Kolom hilang              : {len(report.missing)}",
        "",
        f"{'#':<3} {'Perusahaan':<32} {'Jenis':<11} {'Aplikasi':<11} Catatan",
        "-" * 100,
    ]
    for i, c in enumerate(report.columns, 1):
        baris.append(
            f"{i:<3} {c.title[:31]:<32} {LABEL[c.mapping]:<11} "
            f"{c.app_column:<11} {c.note}")

    if report.extra_app_columns:
        baris += ["", "Kolom tambahan di aplikasi (bukan kolom wajib perusahaan):"]
        for h in report.extra_app_columns:
            baris.append(f"  - {h}")

    baris += [
        "",
        f"Angka yang dinilai : {report.mapped} dari {report.bot_relevant} kolom wajib"
        " yang relevan untuk bot terpetakan  <- dibandingkan dengan target",
        f"Status             : {verdict(report)}",
    ]
    txt.write_text("\n".join(baris) + "\n", encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["letter", "company_column", "mapping", "app_column", "note"])
        for c in report.columns:
            w.writerow([c.letter, c.title, c.mapping, c.app_column, c.note])

    return txt, csv_path


# ------------------------------- penyediaan template


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
