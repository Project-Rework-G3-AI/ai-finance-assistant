"""Test SC-06: kolom wajib cash report terpetakan semua.

Yang diuji hanya kriteria SC-06 dari BRD. Tidak ada test tentang gaya kode.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc06_columns as sc06

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / sc06.TEMPLATE_DIR

pytestmark = pytest.mark.skipif(
    not TEMPLATE_DIR.exists() or not any(TEMPLATE_DIR.glob("*.xlsx")),
    reason="template perusahaan belum diunduh; jalankan tests/_sc06_run.py --download")


# ------------------------------- membaca template perusahaan


def test_company_header_is_read_from_the_real_template():
    """Kolom wajib dibaca dari berkas perusahaan, bukan daftar salinan."""
    berkas = sorted(TEMPLATE_DIR.glob("*.xlsx"))
    assert len(berkas) == 3, f"harus ada 3 berkas template, ada {len(berkas)}"

    headers = sc06.read_all_company_headers(TEMPLATE_DIR)
    assert len(headers) == 3
    for nama, kolom in headers.items():
        assert "TANGGAL TRANSAKSI" in kolom, f"{nama} tidak memuat kolom wajib"
        assert len(kolom) == 10, f"{nama} memuat {len(kolom)} kolom, bukan 10"


def test_all_templates_agree_on_the_required_columns():
    """Ketiga berkas harus sepakat; kalau tidak, tidak ada dasar memilih."""
    headers = sc06.read_all_company_headers(TEMPLATE_DIR)
    daftar = list(headers.values())
    for kolom in daftar[1:]:
        assert kolom == daftar[0], "berkas template tidak sepakat soal kolom wajib"


def test_header_is_found_by_content_not_by_fixed_row():
    """Berkas Operasional menaruh header di baris 4, yang lain di baris 5."""
    operasional = TEMPLATE_DIR / (
        "Cash Report Operasional-PT Lokal Komoditi Indonesia 2026.xlsx")
    if not operasional.exists():
        pytest.skip("berkas Operasional tidak ada")

    import openpyxl

    wb = openpyxl.load_workbook(operasional, data_only=True)
    try:
        baris_header = set()
        for nama in wb.sheetnames:
            ws = wb[nama]
            for r in range(1, 11):
                vals = [str(ws.cell(r, c).value or "").strip() for c in range(1, 12)]
                if "TANGGAL TRANSAKSI" in vals:
                    baris_header.add(r)
                    break
    finally:
        wb.close()

    # Kalau semua header ada di baris yang sama, test ini tidak membuktikan apa
    # pun soal pencarian berbasis isi.
    assert baris_header, "header tidak ditemukan sama sekali"
    kolom = sc06.read_company_header(operasional)
    assert "TANGGAL TRANSAKSI" in kolom


# ------------------------------- kolom aplikasi


def test_app_headers_come_from_the_writer_not_a_copy():
    """Kolom aplikasi dibaca dari modul yang menulis, bukan disalin di sini."""
    kolom = sc06.read_app_headers()

    from cash_report.build_template import TRANSAKSI_HEADERS

    assert kolom == list(TRANSAKSI_HEADERS)


# ------------------------------- pemetaan


def test_every_required_column_has_an_explicit_decision():
    """Setiap kolom wajib punya keputusan tertulis, bukan tebakan nama."""
    report = sc06.compute(TEMPLATE_DIR)
    for kolom in report.columns:
        assert kolom.mapping in sc06.LABEL, (
            f"kolom '{kolom.title}' tidak punya keputusan pemetaan")
        if kolom.mapping == "missing":
            assert kolom.note, (
                f"kolom '{kolom.title}' ditandai hilang tanpa alasan tertulis")


def test_mapped_column_must_really_exist_in_the_output():
    """Kolom yang diklaim terpetakan harus ada di keluaran aplikasi."""
    report = sc06.compute(TEMPLATE_DIR)
    huruf = [chr(ord("A") + i) for i in range(len(report.app_headers))]
    for kolom in report.columns:
        if kolom.mapping in ("missing", "not_bot_data"):
            continue
        target = kolom.app_column.split("!")[0]
        if "!" in kolom.app_column:
            assert kolom.app_column in sc06.OTHER_SHEET_COLUMNS
        else:
            assert target in huruf, (
                f"kolom '{kolom.title}' diklaim di {kolom.app_column}, "
                f"padahal keluaran hanya punya {huruf}")


def test_one_app_column_cannot_stand_for_two_required_columns():
    """Satu kolom aplikasi tidak boleh mewakili dua kolom wajib berbeda.

    Kolom A aplikasi berisi tanggal transaksi, yang sudah menjadi wakil kolom
    B perusahaan. Memakainya lagi untuk kolom A perusahaan akan membuat kolom
    wajib tampak terpetakan padahal isinya bukan.
    """
    report = sc06.compute(TEMPLATE_DIR)
    pemakaian: dict[str, list[str]] = {}
    for kolom in report.columns:
        if kolom.mapping in ("missing", "not_bot_data"):
            continue
        pemakaian.setdefault(kolom.app_column, []).append(kolom.title)

    for app_col, titles in pemakaian.items():
        # Kolom E/F perusahaan sama-sama sah memakai kolom Kantong, karena
        # aplikasi memecah transfer menjadi dua baris: satu baris membawa
        # kantong asal, satu baris membawa kantong tujuan.
        if app_col == "B" and set(titles) == {
                "KETERANGAN UANG MASUK", "KETERANGAN UANG KELUAR"}:
            continue
        assert len(titles) == 1, (
            f"kolom aplikasi {app_col} dipakai oleh {len(titles)} kolom wajib: {titles}")


# ------------------------------- penilaian


def test_measurement_counts_required_columns_not_app_columns():
    """Penyebutnya kolom wajib perusahaan, bukan 11 kolom aplikasi."""
    report = sc06.compute(TEMPLATE_DIR)
    assert report.required == 10
    # Setiap kolom wajib masuk tepat satu keranjang.
    assert (report.mapped + len(report.missing) + len(report.not_bot_data)
            == report.required)
    # Kolom yang diisi manusia tetap dihitung, tetapi tidak di penyebut bot.
    assert report.bot_relevant == report.required - len(report.not_bot_data)


def test_columns_filled_by_people_are_reported_not_hidden():
    """Kolom yang bukan data bot tetap muncul di laporan, bukan disembunyikan.

    Menghapusnya dari daftar akan membuat angka tampak lebih baik tanpa
    menjelaskan apa pun. Yang benar: tampilkan, beri alasan, dan keluarkan dari
    penyebut bot secara terbuka.
    """
    report = sc06.compute(TEMPLATE_DIR)
    for kolom in report.not_bot_data:
        assert kolom.note, f"kolom '{kolom.title}' tidak dijelaskan"
        assert kolom.title in sc06.NOT_BOT_DATA, (
            f"kolom '{kolom.title}' tidak terdaftar sebagai data non-bot")

    out = ROOT / "sc-out-test-nonbot"
    txt, _ = sc06.write_report(report, out)
    try:
        isi = txt.read_text(encoding="utf-8")
        for kolom in report.not_bot_data:
            assert kolom.title in isi, (
                f"kolom '{kolom.title}' tidak muncul di laporan")
        assert f"relevan untuk bot" in isi
    finally:
        import shutil
        shutil.rmtree(out, ignore_errors=True)


def test_status_follows_the_brd_target():
    """Target BRD: tidak ada kolom wajib yang hilang."""
    report = sc06.compute(TEMPLATE_DIR)
    if report.missing:
        assert sc06.verdict(report) == "BELUM TERCAPAI"
    else:
        assert sc06.verdict(report) == "TERCAPAI"


def test_a_missing_column_turns_the_verdict_red():
    """Harness harus bisa merah: kolom wajib yang hilang wajib menggagalkan."""
    report = sc06.compute(TEMPLATE_DIR)
    asli = [sc06.ColumnScore(c.letter, c.title, c.mapping, c.app_column, c.note)
            for c in report.columns]

    # Rusak pemetaan satu kolom yang tadinya terpetakan.
    for c in report.columns:
        if c.mapping != "missing":
            c.mapping = "missing"
            c.note = "dirusak sengaja oleh test"
            break

    assert not report.pass_verdict, "kolom hilang tidak menggagalkan penilaian"
    assert sc06.verdict(report) == "BELUM TERCAPAI"

    report.columns = asli


def test_report_states_the_denominator():
    """Laporan harus menyebut angka mana yang dibandingkan dengan target."""
    report = sc06.compute(TEMPLATE_DIR)
    out = ROOT / "sc-out-test"
    txt, csv_path = sc06.write_report(report, out)
    try:
        isi = txt.read_text(encoding="utf-8")
        assert f"{report.mapped} dari {report.bot_relevant}" in isi
        assert "dibandingkan dengan target" in isi
        assert "Status" in isi
        # CSV memuat satu baris per kolom wajib
        baris = csv_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(baris) == report.required + 1
    finally:
        import shutil
        shutil.rmtree(out, ignore_errors=True)


# ------------------------------- integrasi runner


def test_sc06_needs_no_credentials(monkeypatch):
    """SC-06 gratis: tidak boleh menyentuh kredensial atau jaringan."""
    for var in ("AI_API_KEY", "GOOGLE_OAUTH_REFRESH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)

    report = sc06.compute(TEMPLATE_DIR)
    assert report.required == 10
