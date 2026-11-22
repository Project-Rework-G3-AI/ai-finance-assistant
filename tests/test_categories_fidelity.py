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
    hasil = []
    for f in sorted(Path(DATASET_DIR).glob("*.xlsx")):
        with zipfile.ZipFile(f) as z:
            for part, nama in _sheet_map(z).items():
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
                    potongan = re.findall(r'"([^"]*)"', _unesc(f1.group(1)))
                    nilai = [x.strip() for x in "".join(potongan).split(",") if x.strip()]
                    if nilai:
                        hasil.append((f.name, nama, sq, nilai))
    return hasil


@pytest.fixture(scope="module")
def dataset() -> set[str]:
    blocks = _blocks()
    assert blocks, f"tidak ada dropdown kolom D ditemukan di {DATASET_DIR}"
    nilai: set[str] = set()
    for _, _, _, kategori in blocks:
        nilai |= set(kategori)
    nilai.discard(HEADER)
    return nilai


@pytest.fixture(scope="module")
def isi_sel() -> set[str]:
    openpyxl = pytest.importorskip("openpyxl")
    hasil: set[str] = set()
    for f in sorted(Path(DATASET_DIR).glob("*.xlsx")):
        wb = openpyxl.load_workbook(f, data_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(min_col=4, max_col=4, values_only=True):
                v = row[0]
                if isinstance(v, str) and v.strip():
                    hasil.add(" ".join(v.split()))
        wb.close()
    hasil.discard(HEADER)
    return hasil


def test_setiap_kategori_dataset_dikenal_repo(dataset):
    """Tidak boleh ada kategori perusahaan yang jatuh ke Perlu Ditinjau."""
    tidak = sorted(k for k in dataset if C.normalize(k) == C.PERLU_DITINJAU)
    assert not tidak, (
        "kategori dataset tidak dikenali repo:\n  " + "\n  ".join(tidak))


def test_setiap_kategori_repo_ada_di_dataset(dataset):
    """Tidak boleh ada nama kategori yang dikarang.

    Satu-satunya pengecualian adalah penanda internal, yang dideklarasikan
    eksplisit dan tidak pernah ditawarkan ke model.
    """
    karangan = sorted(k for k in C.KATEGORI
                      if k != C.PERLU_DITINJAU and k not in dataset)
    assert not karangan, (
        "kategori repo tidak ada di dataset (dikarang?):\n  " + "\n  ".join(karangan))


def test_isi_sel_tidak_di_luar_dropdown(dataset, isi_sel):
    """Nilai kategori yang diketik manual di luar dropdown akan lolos dari audit."""
    luar = sorted(isi_sel - dataset)
    assert not luar, (
        "nilai kolom D di luar dropdown:\n  " + "\n  ".join(repr(x) for x in luar))


def test_penanda_internal_tidak_ditawarkan_ke_model():
    assert C.PERLU_DITINJAU not in C.KATEGORI_UNTUK_MODEL
    assert C.PERLU_DITINJAU not in C.PROMPT_KATEGORI.split(", ")


def test_saldo_awal_dikenali_tapi_tidak_ditawarkan():
    assert C.normalize("Saldo Awal") == "Saldo Awal"
    assert "Saldo Awal" not in C.KATEGORI_UNTUK_MODEL


def test_setiap_item_model_bisa_dinormalkan_kembali():
    """Normalisasi harus idempoten: nama final tidak boleh berubah lagi."""
    for k in C.KATEGORI_UNTUK_MODEL:
        assert C.normalize(k) == k, f"tidak idempoten: {k!r}"


def test_alias_tidak_menunjuk_ke_nama_yang_tidak_ada():
    for a, t in C.ALIAS.items():
        assert t in C.KATEGORI, f"alias {a!r} -> {t!r} yang tidak ada di KATEGORI"


def test_tidak_ada_duplikat():
    assert len(C.KATEGORI) == len(set(C.KATEGORI)), "ada kategori duplikat"


def test_setup_memuat_setiap_kategori_tepat_sekali():
    """Setiap kategori harus punya tempat di SETUP, dan hanya satu.

    Duplikat antar kolom pernah terjadi: "Transfer Antar Bank" masuk kolom
    pendapatan sekaligus pengeluaran, sehingga admin melihatnya dua kali di
    dropdown dengan makna berbeda. Tes ini mengunci susunan kolomnya.
    """
    from cash_report import build_template as BT

    kolom = {
        "KATEGORI PENDAPATAN": BT.KAT_INCOME,
        "KATEGORI NERACA": BT.KAT_NERACA,
        "KATEGORI PENGELUARAN": BT.KAT_EXPENSE,
        "KATEGORI LAIN": BT.KAT_LAIN,
    }
    semua = [k for isi in kolom.values() for k in isi]

    dobel = sorted({k for k in semua if semua.count(k) > 1})
    assert not dobel, f"kategori muncul di lebih dari satu kolom SETUP: {dobel}"

    hilang = [k for k in C.KATEGORI if k not in semua]
    assert not hilang, f"kategori tidak punya tempat di SETUP: {hilang}"

    asing = sorted(set(semua) - set(C.KATEGORI))
    assert not asing, f"SETUP memuat kategori di luar KATEGORI: {asing}"


def test_dropdown_transaksi_merujuk_daftar_lengkap():
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
    rentang = req["rule"]["condition"]["values"][0]["userEnteredValue"]
    kol = BT._col_letter(BT.KOL_DROPDOWN)
    awal = BT.BARIS_AWAL_DROPDOWN
    akhir = awal + len(BT.KAT_DROPDOWN) - 1
    assert rentang == f"=SETUP!${kol}${awal}:${kol}${akhir}", (
        f"rentang dropdown salah: {rentang}")

    # Kolom Kategori = E (indeks 4), mulai baris 2.
    assert req["range"]["startColumnIndex"] == 4
    assert req["range"]["startRowIndex"] == 1


def test_dropdown_tidak_memblokir_nilai_lama():
    """strict=False: file lama yang memuat nilai di luar daftar tidak jadi galat."""
    from cash_report import build_template as BT

    assert BT._validasi_dropdown(1)["setDataValidation"]["rule"]["strict"] is False
