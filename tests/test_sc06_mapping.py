"""Test SC-06: hasil pencatatan memetakan seluruh kolom wajib cash report.

Yang diuji hanya kriteria SC-06 dari BRD. Tidak ada test tentang gaya kode.

Seluruh test di sini gratis: tidak memanggil model dan tidak menyentuh jaringan.
Pengukuran pada data asli dijalankan terpisah lewat `tests/_sc06_run.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc06_mapping as sc06

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / sc06.TEMPLATE_DIR

# Kalau template belum diunduh, seluruh test yang membacanya dilewati dengan
# alasan jelas, bukan gagal.
butuh_template = pytest.mark.skipif(
    not (TEMPLATES / sc06.TEMPLATE_FILES[0]).is_file(),
    reason="template perusahaan belum ada; jalankan --download",
)

BASE = {
    "tanggal": "2026-01-05 10:00:00",
    "keterangan": "Beli tepung",
    "nominal": 195000,
    "arah": "keluar",
    "kategori": "Bahan Baku",
    "bank": "BNI",
    "kantong_tujuan": "",
    "sumber_file": "uji.jpg",
}


def raw(**ubah) -> dict:
    nilai = dict(BASE)
    nilai.update(ubah)
    return nilai


def baris_untuk(**ubah) -> list[dict]:
    return [{"file": "uji.jpg", "raw": raw(**ubah), "error": ""}]


# ------------------------------------- tiruan penulisan baris = produksi


def test_written_rows_matches_production():
    """Tiruan penulisan baris harus sama dengan `main.write_cash_report`.

    Kalau keduanya berbeda, angka SC-06 mengukur tiruan, bukan aplikasi. Ini
    penjaga fidélitas: test hijau tidak berarti apa-apa bila harnessnya sendiri
    menyimpang dari produksi.
    """
    import main

    kelas = type("W", (), {
        "title": "TRANSAKSI",
        "col_values": lambda s, i: [],
        "update": lambda s, **k: s.__dict__.setdefault("vals", k["values"]),
        "format": lambda s, *a, **k: None,
    })
    for kasus in (
        {"arah": "masuk", "bank": "", "kantong_tujuan": ""},
        {"arah": "transfer", "bank": "", "kantong_tujuan": "BNI"},
        {"arah": "transfer", "bank": "BNI", "kantong_tujuan": "BRI"},
        {"arah": "transfer", "bank": "", "kantong_tujuan": ""},
        {"arah": "keluar", "bank": "BNI", "kantong_tujuan": ""},
    ):
        rec = dict(raw(**kasus), ref_id="tg:uji", catatan="")
        ws = kelas()
        main._find_or_create_folder = lambda *a, **k: {"id": "f"}
        main._find_or_create_spreadsheet = lambda *a, **k: {"id": "s"}
        main._open_spreadsheet = lambda *a, **k: type(
            "Sh", (), {"worksheet": lambda s, n: ws})()
        main._drive_ready = lambda: False
        main.CR_FOLDER_ID = "x"
        main.CR_TEMPLATE_ID = "y"

        main.write_cash_report(rec, b"", "uji.jpg")
        produksi = ws.vals
        tiruan = sc06.written_rows(dict(raw(**kasus), sumber_file="uji.jpg"))

        assert len(produksi) == len(tiruan), (
            f"jumlah baris beda untuk {kasus}: produksi {len(produksi)} "
            f"vs tiruan {len(tiruan)}")
        for p, t in zip(produksi, tiruan):
            # Kolom B (Kantong), C (Masuk), D (Keluar) adalah inti pemetaan.
            assert p[1] == t[1], f"Kantong beda: {p[1]!r} vs {t[1]!r}"
            assert str(p[2]) == str(t[2]), f"Masuk beda: {p[2]!r} vs {t[2]!r}"
            assert str(p[3]) == str(t[3]), f"Keluar beda: {p[3]!r} vs {t[3]!r}"
            assert p[4] == t[4], f"Kategori beda: {p[4]!r} vs {t[4]!r}"


def test_transfer_writes_two_rows():
    """Transfer menulis dua baris: keluar dari kantong asal, masuk ke tujuan."""
    assert len(sc06.written_rows(raw(arah="transfer", bank="BNI",
                                     kantong_tujuan="BRI"))) == 2


def test_ordinary_transaction_writes_one_row():
    assert len(sc06.written_rows(raw(arah="masuk"))) == 1
    assert len(sc06.written_rows(raw(arah="keluar"))) == 1


def test_transfer_without_target_falls_back_to_one_row():
    """Transfer tanpa kantong tujuan tidak bisa dipecah dua baris."""
    assert len(sc06.written_rows(raw(arah="transfer", kantong_tujuan=""))) == 1


# ------------------------------------------------- bagian 1: susunan kolom


@butuh_template
def test_company_template_has_ten_required_columns():
    header = sc06.read_company_header(TEMPLATES / sc06.TEMPLATE_FILES[0])
    assert len(header) == 10
    assert "TANGGAL TRANSAKSI" in header


@butuh_template
def test_header_is_found_by_content_not_row_number():
    """Berkas Operasional menaruh header di baris 4, yang lain di baris 5."""
    for nama in sc06.TEMPLATE_FILES:
        header = sc06.read_company_header(TEMPLATES / nama)
        assert header, f"header tidak ditemukan di {nama}"
        assert len(header) == 10, f"{nama}: {len(header)} kolom"


@butuh_template
def test_every_company_column_has_a_decision():
    """Tidak boleh ada kolom perusahaan yang belum diputuskan nasibnya."""
    for judul in sc06.read_company_header(TEMPLATES / sc06.TEMPLATE_FILES[0]):
        assert judul in sc06.MAPPING, f"kolom '{judul}' belum punya keputusan"
        assert sc06.MAPPING[judul][0] in sc06.LABEL


@butuh_template
def test_columns_mapped_to_app_must_really_exist():
    """Pemetaan tidak boleh mengklaim kolom yang tidak ada di aplikasi."""
    app = sc06.read_app_headers()
    for judul, (jenis, kolom, _) in sc06.MAPPING.items():
        if jenis in ("missing", "not_bot_data"):
            continue
        assert sc06._column_exists(kolom, app), (
            f"kolom '{judul}' dipetakan ke {kolom!r} yang tidak ada di aplikasi")


@butuh_template
def test_admin_column_is_excluded_from_the_denominator():
    """Kolom yang diisi manusia bukan data bot, jadi tidak dinilai."""
    laporan = sc06.compute(baris_untuk())
    judul = [c.title for c in laporan.bot_relevant]
    assert sc06.NOT_BOT_DATA not in judul
    assert len(laporan.bot_relevant) == 9


@butuh_template
def test_missing_column_turns_the_verdict_red(monkeypatch):
    """Satu kolom hilang berarti target tidak tercapai."""
    monkeypatch.setitem(sc06.MAPPING, "KATEGORI", ("missing", "", "dirusak"))
    laporan = sc06.compute(baris_untuk())
    assert len(laporan.missing_columns) == 1
    assert sc06.verdict(laporan) == "BELUM TERCAPAI"


# --------------------------------------- bagian 2: kelengkapan per baris


@butuh_template
def test_complete_transaction_has_no_missing_column():
    laporan = sc06.compute(baris_untuk())
    assert laporan.total_rows == 1
    assert laporan.complete_rows == 1
    assert laporan.rows[0].missing == []


@butuh_template
def test_unreadable_nominal_is_counted_missing():
    """Nominal kosong membuat DEBET dan KREDIT dua-duanya kosong."""
    laporan = sc06.compute(baris_untuk(nominal=0))
    assert laporan.complete_rows == 0
    assert any("DEBET" in m for m in laporan.rows[0].missing)
    assert sc06.verdict(laporan) == "BELUM TERCAPAI"


@butuh_template
def test_unreadable_category_is_counted_missing():
    laporan = sc06.compute(baris_untuk(kategori=""))
    assert laporan.complete_rows == 0
    assert "KATEGORI" in laporan.rows[0].missing


@butuh_template
def test_unreadable_description_is_counted_missing():
    laporan = sc06.compute(baris_untuk(keterangan=""))
    assert "KETERANGAN" in laporan.rows[0].missing


@butuh_template
def test_paired_columns_are_not_both_required():
    """Satu baris hanya mengisi DEBET atau KREDIT, tidak pernah keduanya.

    Menuntut keduanya terisi akan membuat setiap baris dianggap kurang, dan itu
    kesalahan hitung, bukan temuan.
    """
    laporan = sc06.compute(baris_untuk(arah="masuk"))
    baris = sc06.row_as_columns(sc06.written_rows(raw(arah="masuk"))[0])
    assert str(baris["DEBET"]).strip()
    assert not str(baris["KREDIT"] or "").strip()
    assert laporan.complete_rows == 1


@butuh_template
def test_drive_column_is_excluded_when_drive_is_off():
    """LAMPIRAN NOTA berisi URL Drive; tanpa Drive aktif ia tidak diukur."""
    laporan = sc06.compute(baris_untuk())
    assert laporan.drive_enabled is False
    assert all(sc06.DRIVE_COLUMN not in r.missing for r in laporan.rows)


@butuh_template
def test_transfer_produces_two_scored_rows():
    laporan = sc06.compute(baris_untuk(arah="transfer", kantong_tujuan="BRI"))
    assert laporan.total_rows == 2
    assert laporan.complete_rows == 2


# --------------------------------------------------------------- agregasi


@butuh_template
def test_failed_image_is_not_counted_as_complete():
    laporan = sc06.compute([
        {"file": "a.jpg", "raw": raw(), "error": ""},
        {"file": "b.jpg", "raw": {}, "error": "HTTP 500"},
    ])
    assert laporan.failed_images == 1
    assert sc06.verdict(laporan) == "GAGAL DIUKUR"


@butuh_template
def test_empty_run_is_not_a_pass():
    laporan = sc06.compute([])
    assert sc06.verdict(laporan) == "BELUM DIUKUR"


@butuh_template
def test_missing_template_is_not_a_pass(tmp_path):
    """Tanpa template perusahaan, kriteria ini belum bisa diukur."""
    with pytest.raises(FileNotFoundError):
        sc06.compute(baris_untuk(), template_dir=tmp_path)


# ----------------------------------------------------------------- laporan


@butuh_template
def test_report_states_the_denominator_and_the_verdict(tmp_path):
    laporan = sc06.compute(baris_untuk())
    txt, csv_path = sc06.write_report(laporan, tmp_path)
    isi = txt.read_text(encoding="utf-8")
    assert "1 dari 1" in isi
    assert "dibandingkan dengan target" in isi
    assert "BAGIAN 1" in isi and "BAGIAN 2" in isi
    assert "Status" in isi
    assert len(csv_path.read_text(encoding="utf-8").strip().splitlines()) == 2


@butuh_template
def test_report_names_which_row_and_column_are_missing(tmp_path):
    laporan = sc06.compute([{"file": "hilang.jpg",
                             "raw": raw(nominal=0), "error": ""}])
    txt, _ = sc06.write_report(laporan, tmp_path)
    isi = txt.read_text(encoding="utf-8")
    assert "hilang.jpg" in isi
    assert "DEBET" in isi


@butuh_template
def test_report_says_drive_column_was_not_measured(tmp_path):
    laporan = sc06.compute(baris_untuk())
    txt, _ = sc06.write_report(laporan, tmp_path)
    assert "LAMPIRAN NOTA tidak diukur" in txt.read_text(encoding="utf-8")
