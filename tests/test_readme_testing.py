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


def label(criteria: str) -> str:
    """`sc01` -> `SC-01`, sesuai cara README menulisnya."""
    return criteria[:2].upper() + "-" + criteria[2:]


@pytest.fixture(scope="module")
def text() -> str:
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def testing_section(text: str) -> str:
    """Hanya bagian ## Pengujian, supaya tabel lain tidak ikut tertangkap."""
    start = text.index("## Pengujian")
    try:
        end = text.index("\n## ", start + 5)
    except ValueError:
        end = len(text)
    return text[start:end]


# --------------------------------------------- setiap kriteria punya flag

def test_every_available_criterion_has_its_own_flag_in_the_readme(testing_section):
    """Setiap kriteria yang terdaftar harus punya baris `--scNN` di README."""
    missing_items = [k for k in sc_runner.AVAILABLE_CRITERIA
              if f"--{k}" not in testing_section]
    assert not missing_items, f"README tidak menyebut flag: {missing_items}"


def test_every_available_criterion_has_a_status_row(testing_section):
    # README menulis "SC-01", bukan "SC01"; nama kriteria di kode tanpa tanda
    # hubung, jadi labelnya harus disusun, bukan sekadar di-upper-kan.
    missing_items = [k for k in sc_runner.AVAILABLE_CRITERIA
              if f"| {label(k)} |" not in testing_section]
    assert not missing_items, f"README tidak punya baris tabel untuk: {missing_items}"


def test_available_criteria_are_not_marked_as_not_yet_done(testing_section):
    """Kriteria yang sudah bisa dijalankan tidak boleh ditulis "belum".

    Ini cacat aslinya: SC-03 dan SC-04 sudah jalan, README masih bilang belum.
    """
    wrong = []
    for k in sc_runner.AVAILABLE_CRITERIA:
        pattern = re.compile(rf"\| {label(k)} \|[^|]*\|[^|]*\|\s*belum")
        if pattern.search(testing_section):
            wrong.append(k)
    assert not wrong, f"README menandai sudah-tersedia sebagai 'belum': {wrong}"


# --------------------------------------------- pengukur khusus disebut

def test_readme_names_the_dedicated_harnesses(testing_section):
    """SC-03 dan SC-04 tidak bisa dihitung dari hasil ekstraksi.

    README harus menyebut pengukurnya, karena tanpa itu pembaca tidak akan tahu
    bahwa `--sc03`/`--sc04` hanya merangkum sampel yang belum tentu ada.
    """
    for name in ("_sc03_run.py", "_sc04_run.py"):
        assert name in testing_section, f"README tidak menyebut {name}"


def test_readme_does_not_claim_all_criteria_are_free(testing_section):
    """Kalimat "menambah kriteria tidak menambah biaya" dulu menyesatkan.

    Itu benar untuk SC-01/SC-02, tetapi salah untuk SC-03/SC-04 yang punya
    pengukuran sendiri. Yang dilarang adalah pernyataan tanpa pengecualian.
    """
    pattern = re.compile(
        r"Menambah kriteria tidak menambah biaya, karena semuanya membaca")
    assert not pattern.search(testing_section), (
        "README menyatakan semua kriteria gratis; SC-03/SC-04 punya pengukuran "
        "sendiri dan harus disebut pengecualiannya")


# --------------------------------------------- berkas keluaran terdokumentasi

def test_every_reported_output_file_is_documented(testing_section):
    """Berkas yang ditulis runner harus ada di tabel keluaran README."""
    output_value = [f"sc0{n}_report.txt" for n in range(1, 8)]
    output_value += [f"sc0{n}_metrics.json" for n in range(1, 8)]
    missing_keys = [n for n in output_value
              if n in _files_written_by_runner() and n not in testing_section]
    assert not missing_keys, f"README tidak mendokumentasikan keluaran: {missing_keys}"


def _files_written_by_runner() -> set[str]:
    """Ambil nama berkas laporan yang benar-benar ditulis kode runner."""
    source = (Path(__file__).resolve().parent / "sc_runner.py").read_text(
        encoding="utf-8")
    return set(re.findall(r'"(sc0\d_report\.txt|sc0\d_metrics\.json)"', source))


# --------------------------------------------- dokumen hasil dirujuk

def test_each_measured_criterion_links_its_result_document(testing_section):
    """Kalau dokumen hasilnya ada, README harus menunjuk ke sana."""
    for k in sc_runner.AVAILABLE_CRITERIA:
        doc = ROOT / "docs" / f"{k}-hasil-evaluasi.md"
        if doc.exists():
            assert f"{k}-hasil-evaluasi.md" in testing_section, (
                f"README tidak menautkan {doc.name}")


# --------------------------------------------- variabel lingkungan dijelaskan

def test_sandbox_variables_are_explained(testing_section):
    """SC-03 menolak jalan tanpa variabel sandbox; itu harus bisa diketahui."""
    for name in ("SC03_SANDBOX_FOLDER", "SC03_SANDBOX_TEMPLATE"):
        assert name in testing_section, f"README tidak menyebut {name}"


def test_every_env_example_variable_used_by_tests_is_mentioned():
    """Variabel yang dibaca kode test harus muncul di README atau .env.example.

    Yang diperiksa hanya variabel SC, karena variabel aplikasi sudah punya
    bagian sendiri di README.
    """
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    used = set()
    for path in (Path(__file__).resolve().parent).glob("sc0*.py"):
        used |= set(re.findall(r'"(SC0\d_[A-Z_]+)"', path.read_text(
            encoding="utf-8")))
    missing_keys = [v for v in used if f"{v}=" not in env_example]
    assert not missing_keys, f".env.example tidak memuat: {missing_keys}"
