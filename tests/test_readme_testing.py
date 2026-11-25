"""README harus ikut berubah saat kriteria bertambah.

Cacat yang dikunci di sini pernah terjadi: SC-03 dan SC-04 sudah diukur dan
di-commit, tetapi README masih menulis status "belum" dan tidak menyebut cara
menjalankan pengukurnya. Pembaca yang mengikuti README akan mengira kriteria itu
belum ada.

Test ini membandingkan README dengan kenyataan kode, bukan dengan daftar yang
ditulis ulang di sini. Jadi menambah kriteria baru tanpa memperbarui README akan
membuat test gagal, bukan lolos diam-diam.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc_runner  # noqa: E402

README = ROOT / "README.md"


def label(kriteria: str) -> str:
    """`sc01` -> `SC-01`, sesuai cara README menulisnya."""
    return kriteria[:2].upper() + "-" + kriteria[2:]


@pytest.fixture(scope="module")
def teks() -> str:
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def bagian_pengujian(teks: str) -> str:
    """Hanya bagian ## Pengujian, supaya tabel lain tidak ikut tertangkap."""
    awal = teks.index("## Pengujian")
    try:
        akhir = teks.index("\n## ", awal + 5)
    except ValueError:
        akhir = len(teks)
    return teks[awal:akhir]


# --------------------------------------------- setiap kriteria punya flag

def test_every_available_criterion_has_its_own_flag_in_the_readme(bagian_pengujian):
    """Setiap kriteria yang terdaftar harus punya baris `--scNN` di README."""
    kurang = [k for k in sc_runner.AVAILABLE_CRITERIA
              if f"--{k}" not in bagian_pengujian]
    assert not kurang, f"README tidak menyebut flag: {kurang}"


def test_every_available_criterion_has_a_status_row(bagian_pengujian):
    # README menulis "SC-01", bukan "SC01"; nama kriteria di kode tanpa tanda
    # hubung, jadi labelnya harus disusun, bukan sekadar di-upper-kan.
    kurang = [k for k in sc_runner.AVAILABLE_CRITERIA
              if f"| {label(k)} |" not in bagian_pengujian]
    assert not kurang, f"README tidak punya baris tabel untuk: {kurang}"


def test_available_criteria_are_not_marked_as_not_yet_done(bagian_pengujian):
    """Kriteria yang sudah bisa dijalankan tidak boleh ditulis "belum".

    Ini cacat aslinya: SC-03 dan SC-04 sudah jalan, README masih bilang belum.
    """
    salah = []
    for k in sc_runner.AVAILABLE_CRITERIA:
        pola = re.compile(rf"\| {label(k)} \|[^|]*\|[^|]*\|\s*belum")
        if pola.search(bagian_pengujian):
            salah.append(k)
    assert not salah, f"README menandai sudah-tersedia sebagai 'belum': {salah}"


# --------------------------------------------- pengukur khusus disebut

def test_readme_names_the_dedicated_harnesses(bagian_pengujian):
    """SC-03 dan SC-04 tidak bisa dihitung dari hasil ekstraksi.

    README harus menyebut pengukurnya, karena tanpa itu pembaca tidak akan tahu
    bahwa `--sc03`/`--sc04` hanya merangkum sampel yang belum tentu ada.
    """
    for nama in ("_sc03_run.py", "_sc04_run.py"):
        assert nama in bagian_pengujian, f"README tidak menyebut {nama}"


def test_readme_does_not_claim_all_criteria_are_free(bagian_pengujian):
    """Kalimat "menambah kriteria tidak menambah biaya" dulu menyesatkan.

    Itu benar untuk SC-01/SC-02, tetapi salah untuk SC-03/SC-04 yang punya
    pengukuran sendiri. Yang dilarang adalah pernyataan tanpa pengecualian.
    """
    pola = re.compile(
        r"Menambah kriteria tidak menambah biaya, karena semuanya membaca")
    assert not pola.search(bagian_pengujian), (
        "README menyatakan semua kriteria gratis; SC-03/SC-04 punya pengukuran "
        "sendiri dan harus disebut pengecualiannya")


# --------------------------------------------- berkas keluaran terdokumentasi

def test_every_reported_output_file_is_documented(bagian_pengujian):
    """Berkas yang ditulis runner harus ada di tabel keluaran README."""
    keluaran = [f"sc0{n}_report.txt" for n in range(1, 8)]
    keluaran += [f"sc0{n}_metrics.json" for n in range(1, 8)]
    hilang = [n for n in keluaran
              if n in _berkas_yang_ditulis() and n not in bagian_pengujian]
    assert not hilang, f"README tidak mendokumentasikan keluaran: {hilang}"


def _berkas_yang_ditulis() -> set[str]:
    """Ambil nama berkas laporan yang benar-benar ditulis kode runner."""
    sumber = (Path(__file__).resolve().parent / "sc_runner.py").read_text(
        encoding="utf-8")
    return set(re.findall(r'"(sc0\d_report\.txt|sc0\d_metrics\.json)"', sumber))


# --------------------------------------------- dokumen hasil dirujuk

def test_each_measured_criterion_links_its_result_document(bagian_pengujian):
    """Kalau dokumen hasilnya ada, README harus menunjuk ke sana."""
    for k in sc_runner.AVAILABLE_CRITERIA:
        dok = ROOT / "docs" / f"{k}-hasil-evaluasi.md"
        if dok.exists():
            assert f"{k}-hasil-evaluasi.md" in bagian_pengujian, (
                f"README tidak menautkan {dok.name}")


# --------------------------------------------- variabel lingkungan dijelaskan

def test_sandbox_variables_are_explained(bagian_pengujian):
    """SC-03 menolak jalan tanpa variabel sandbox; itu harus bisa diketahui."""
    for nama in ("SC03_SANDBOX_FOLDER", "SC03_SANDBOX_TEMPLATE"):
        assert nama in bagian_pengujian, f"README tidak menyebut {nama}"


def test_every_env_example_variable_used_by_tests_is_mentioned():
    """Variabel yang dibaca kode test harus muncul di README atau .env.example.

    Yang diperiksa hanya variabel SC, karena variabel aplikasi sudah punya
    bagian sendiri di README.
    """
    env_contoh = (ROOT / ".env.example").read_text(encoding="utf-8")
    dipakai = set()
    for berkas in (Path(__file__).resolve().parent).glob("sc0*.py"):
        dipakai |= set(re.findall(r'"(SC0\d_[A-Z_]+)"', berkas.read_text(
            encoding="utf-8")))
    hilang = [v for v in dipakai if f"{v}=" not in env_contoh]
    assert not hilang, f".env.example tidak memuat: {hilang}"
