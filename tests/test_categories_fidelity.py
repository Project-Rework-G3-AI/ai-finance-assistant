"""Kesetiaan kategori terhadap dataset perusahaan.

Tes ini membaca file Excel asli, bukan salinan daftar. Kebenaran selalu datang
dari sumbernya, sehingga kategori yang dikarang atau yang terlewat akan gagal
di sini.

Bila dataset tidak tersedia (repo publik, dataset privat), seluruh tes
di-skip dengan exit 0 — bukan gagal.

Jalankan:
    DATASET_DIR="/path/ke/Cash Report dan Mutasi Rekening" pytest tests/ -v
"""
from __future__ import annotations

import os
import re
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cash_report import categories as C  # noqa: E402

DATASET_DIR = os.environ.get("DATASET_DIR", "").strip()

pytestmark = pytest.mark.skipif(
    not DATASET_DIR or not Path(DATASET_DIR).is_dir(),
    reason="DATASET_DIR tidak tersedia; dataset perusahaan bersifat privat",
)

UNESC = [("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"),
         ("&amp;", "&")]
HEADER = "KATEGORI"


def _unesc(s: str) -> str:
    for a, b in UNESC:
        s = s.replace(a, b)
    return s


def _sheet_map(z: zipfile.ZipFile) -> dict[str, str]:
    wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "replace")
    rid2t: dict[str, str] = {}
    for m in re.finditer(r'<Relationship[^>]*?Id="(rId\d+)"[^>]*?Target="([^"]+)"', rels):
        rid2t[m.group(1)] = m.group(2)
    for m in re.finditer(r'<Relationship[^>]*?Target="([^"]+)"[^>]*?Id="(rId\d+)"', rels):
        rid2t.setdefault(m.group(2), m.group(1))
    out: dict[str, str] = {}
    for m in re.finditer(r'<sheet[^>]*?name="([^"]*)"[^>]*?r:id="(rId\d+)"', wb):
        target = rid2t.get(m.group(2), "").lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        out[target] = _unesc(m.group(1))
    return out


def _blocks() -> list[tuple[str, str, str, list[str]]]:
    """Semua blok dataValidation kolom D. Satu sheet bisa punya lebih dari satu."""
    result = []
    for f in sorted(Path(DATASET_DIR).glob("*.xlsx")):
        with zipfile.ZipFile(f) as z:
            for part, name in _sheet_map(z).items():
                if part not in z.namelist():
                    continue
                xml = z.read(part).decode("utf-8", "replace")
                for dv in re.findall(r"<dataValidation\b.*?</dataValidation>", xml, re.S):
                    sq = re.search(r'sqref="([^"]*)"', dv)
                    sq = sq.group(1) if sq else ""
                    if not re.match(r"^D\d", sq):
                        continue
                    f1 = re.search(r"<formula1>(.*?)</formula1>", dv, re.S)
                    if not f1:
                        continue
                    segment = re.findall(r'"([^"]*)"', _unesc(f1.group(1)))
                    value = [x.strip() for x in "".join(segment).split(",") if x.strip()]
                    if value:
                        result.append((f.name, name, sq, value))
    return result


@pytest.fixture(scope="module")
def dataset() -> set[str]:
    blocks = _blocks()
    assert blocks, f"tidak ada dropdown kolom D ditemukan di {DATASET_DIR}"
    value: set[str] = set()
    for _, _, _, category in blocks:
        value |= set(category)
    value.discard(HEADER)
    return value


@pytest.fixture(scope="module")
def cell_content() -> set[str]:
    openpyxl = pytest.importorskip("openpyxl")
    result: set[str] = set()
    for f in sorted(Path(DATASET_DIR).glob("*.xlsx")):
        wb = openpyxl.load_workbook(f, data_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(min_col=4, max_col=4, values_only=True):
                v = row[0]
                if isinstance(v, str) and v.strip():
                    result.add(" ".join(v.split()))
        wb.close()
    result.discard(HEADER)
    return result


def test_every_dataset_category_known_to_repo(dataset):
    """Tidak boleh ada kategori perusahaan yang jatuh ke Perlu Ditinjau."""
    not_ok = sorted(k for k in dataset if C.normalize(k) == C.PERLU_DITINJAU)
    assert not not_ok, (
        "kategori dataset tidak dikenali repo:\n  " + "\n  ".join(not_ok))


def test_every_repo_category_in_dataset(dataset):
    """Tidak boleh ada nama kategori yang dikarang.

    Satu-satunya pengecualian adalah penanda internal, yang dideklarasikan
    eksplisit dan tidak pernah ditawarkan ke model.
    """
    fabricated = sorted(k for k in C.KATEGORI
                      if k != C.PERLU_DITINJAU and k not in dataset)
    assert not fabricated, (
        "kategori repo tidak ada di dataset (dikarang?):\n  " + "\n  ".join(fabricated))


def test_cell_content_within_dropdown(dataset, cell_content):
    """Nilai kategori yang diketik manual di luar dropdown akan lolos dari audit."""
    outside = sorted(cell_content - dataset)
    assert not outside, (
        "nilai kolom D di luar dropdown:\n  " + "\n  ".join(repr(x) for x in outside))


def test_internal_marker_not_offered_to_model():
    assert C.PERLU_DITINJAU not in C.KATEGORI_UNTUK_MODEL
    assert C.PERLU_DITINJAU not in C.PROMPT_KATEGORI.split(", ")


def test_opening_balance_known_but_not_offered():
    assert C.normalize("Saldo Awal") == "Saldo Awal"
    assert "Saldo Awal" not in C.KATEGORI_UNTUK_MODEL


def test_every_model_item_can_be_normalised_back():
    """Normalisasi harus idempoten: nama final tidak boleh berubah lagi."""
    for k in C.KATEGORI_UNTUK_MODEL:
        assert C.normalize(k) == k, f"tidak idempoten: {k!r}"


def test_alias_points_to_existing_name():
    for a, t in C.ALIAS.items():
        assert t in C.KATEGORI, f"alias {a!r} -> {t!r} yang tidak ada di KATEGORI"


def test_no_duplicates():
    assert len(C.KATEGORI) == len(set(C.KATEGORI)), "ada kategori duplikat"


def test_setup_loads_every_category_exactly_once():
    """Setiap kategori harus punya tempat di SETUP, dan hanya satu.

    Duplikat antar kolom pernah terjadi: "Transfer Antar Bank" masuk kolom
    pendapatan sekaligus pengeluaran, sehingga admin melihatnya dua kali di
    dropdown dengan makna berbeda. Tes ini mengunci susunan kolomnya.
    """
    from cash_report import build_template as BT

    column = {
        "KATEGORI PENDAPATAN": BT.KAT_INCOME,
        "KATEGORI NERACA": BT.KAT_NERACA,
        "KATEGORI PENGELUARAN": BT.KAT_EXPENSE,
        "KATEGORI LAIN": BT.KAT_LAIN,
    }
    everything = [k for content in column.values() for k in content]

    doubled = sorted({k for k in everything if everything.count(k) > 1})
    assert not doubled, f"kategori muncul di lebih dari satu kolom SETUP: {doubled}"

    missing_keys = [k for k in C.KATEGORI if k not in everything]
    assert not missing_keys, f"kategori tidak punya tempat di SETUP: {missing_keys}"

    foreign = sorted(set(everything) - set(C.KATEGORI))
    assert not foreign, f"SETUP memuat kategori di luar KATEGORI: {foreign}"


def test_transaction_dropdown_uses_full_list():
    """Dropdown kolom Kategori harus memuat ke-31 kategori, tanpa sel kosong.

    Dropdown-nya memakai ONE_OF_RANGE ke SETUP, bukan daftar inline: 31
    kategori sudah 614 karakter, sedangkan batas daftar inline sekitar 256.
    """
    from cash_report import build_template as BT

    assert BT.KAT_DROPDOWN == list(C.KATEGORI), (
        "daftar dropdown tidak sama dengan KATEGORI")
    assert all(isinstance(k, str) and k.strip() for k in BT.KAT_DROPDOWN), (
        "ada entri kosong di daftar dropdown; sel kosong muncul sebagai pilihan")

    # Kolom sumber harus DI LUAR kolom B-E yang berkelompok: kolom itu
    # panjangnya tidak sama, sehingga sel kosongnya jadi pilihan kosong.
    # Batas ini ditulis sebagai angka, bukan diturunkan dari KOL_DROPDOWN,
    # supaya tes tidak ikut berubah ketika konstantanya salah diubah.
    assert BT.KOL_DROPDOWN >= 5, (
        f"kolom sumber dropdown ({BT._col_letter(BT.KOL_DROPDOWN)}) menabrak "
        "kolom B-E yang berkelompok dan berisi sel kosong")
    assert BT.BARIS_AWAL_DROPDOWN > 3, (
        f"baris awal dropdown ({BT.BARIS_AWAL_DROPDOWN}) menabrak header baris 3")

    req = BT._validasi_dropdown(1)["setDataValidation"]
    range_value = req["rule"]["condition"]["values"][0]["userEnteredValue"]
    kol = BT._col_letter(BT.KOL_DROPDOWN)
    start = BT.BARIS_AWAL_DROPDOWN
    end = start + len(BT.KAT_DROPDOWN) - 1
    assert range_value == f"=SETUP!${kol}${start}:${kol}${end}", (
        f"rentang dropdown salah: {range_value}")

    # Kolom Kategori = E (indeks 4), mulai baris 2.
    assert req["range"]["startColumnIndex"] == 4
    assert req["range"]["startRowIndex"] == 1


def test_dropdown_does_not_block_old_value():
    """strict=False: file lama yang memuat nilai di luar daftar tidak jadi galat."""
    from cash_report import build_template as BT

    assert BT._validasi_dropdown(1)["setDataValidation"]["rule"]["strict"] is False
