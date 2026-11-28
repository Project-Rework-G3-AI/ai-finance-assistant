"""Pemilihan kriteria pada runner.

Sebelumnya SC-01 menjadi bawaan sementara SC-02 harus diminta lewat `--sc02`.
Akibatnya `python3 tests/sc_runner.py` dan `python3 tests/sc_runner.py --sc02`
terlihat seperti dua perintah yang tidak sederajat, padahal keduanya mengukur
kriteria yang setara. Test ini mengunci aturan yang sekarang dipakai: tanpa flag
berarti semua kriteria, dan tiap kriteria bisa diminta sendiri-sendiri.

Yang diuji hanya pemilihan kriteria, bukan panggilan model, supaya tetap cepat
dan gratis.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sc_runner import AVAILABLE_CRITERIA, selected_criteria  # noqa: E402


def make_args(**kwargs):
    """Args tiruan dengan semua flag kriteria bernilai False secara bawaan."""
    base = {"sc01": False, "sc02": False, "all": False}
    base.update(kwargs)
    return argparse.Namespace(**base)


# --------------------------------------------------------------- tanpa flag

def test_no_flag_means_every_criterion():
    """Ini inti perbaikannya: tanpa flag harus sama dengan --all."""
    assert selected_criteria(make_args()) == list(AVAILABLE_CRITERIA)


def test_no_flag_matches_all_flag_exactly():
    assert selected_criteria(make_args()) == selected_criteria(make_args(all=True))


# ------------------------------------------------------------ satu kriteria

def test_sc01_flag_selects_only_sc01():
    assert selected_criteria(make_args(sc01=True)) == ["sc01"]


def test_sc02_flag_selects_only_sc02():
    assert selected_criteria(make_args(sc02=True)) == ["sc02"]


def test_all_flag_selects_every_available_criterion():
    assert selected_criteria(make_args(all=True)) == list(AVAILABLE_CRITERIA)


# ------------------------------------------------------------------ cakupan

def test_every_available_criterion_can_be_selected_by_its_own_flag():
    """Kriteria baru harus otomatis punya flag sendiri, bukan hanya SC-01."""
    for name in AVAILABLE_CRITERIA:
        assert selected_criteria(make_args(**{name: True})) == [name]


def test_selection_never_returns_duplicates():
    picked = selected_criteria(make_args(all=True))
    assert len(picked) == len(set(picked))


def test_selection_is_a_copy_not_the_shared_tuple():
    """Mengubah hasil tidak boleh merusak daftar kriteria global."""
    picked = selected_criteria(make_args())
    picked.append("sc99")
    assert "sc99" not in AVAILABLE_CRITERIA


# -------------------------------------------------------- perilaku argparse

def test_conflicting_flags_are_rejected_by_the_parser():
    """--sc01 --sc02 harus ditolak, bukan diam-diam memilih salah satu."""
    from sc_runner import main_cli

    argv = sys.argv
    sys.argv = ["sc_runner.py", "--sc01", "--sc02", "--metrics-only"]
    try:
        with pytest.raises(SystemExit):
            main_cli()
    finally:
        sys.argv = argv


def test_sc01_and_all_cannot_be_combined():
    from sc_runner import main_cli

    argv = sys.argv
    sys.argv = ["sc_runner.py", "--sc01", "--all", "--metrics-only"]
    try:
        with pytest.raises(SystemExit):
            main_cli()
    finally:
        sys.argv = argv


# --------------------------------------------------------------- urutan log

def test_reports_follow_criteria_order_not_hand_written_order():
    """SC-01 harus tampil lebih dulu, sesuai urutan AVAILABLE_CRITERIA.

    Sebelumnya urutan cetak ditulis tangan sebagai dua blok `if` dan blok SC-02
    kebetulan diletakkan lebih dulu, sehingga log terlihat seperti SC-02
    berjalan sebelum SC-01. Yang benar: satu lintasan ekstraksi dipakai
    bersama, jadi urutan log hanya soal penyajian.
    """
    from sc_runner import join_reports, run_reports

    captured = []

    def fake(name):
        def builder(results, out):
            captured.append(name)
            return {"text": f"laporan-{name}"}
        return builder

    import sc_runner
    original = dict(sc_runner.__dict__)
    try:
        sc_runner.write_sc01_report = fake("sc01")
        sc_runner.write_sc02_report = fake("sc02")
        reports = run_reports([], Path("."), ["sc01", "sc02"])
    finally:
        for key in ("write_sc01_report", "write_sc02_report"):
            sc_runner.__dict__[key] = original[key]

    assert captured == ["sc01", "sc02"]
    assert list(reports) == ["sc01", "sc02"]
    text = join_reports(reports)
    assert text.index("laporan-sc01") < text.index("laporan-sc02")


def test_order_is_respected_for_a_single_criterion():
    from sc_runner import run_reports

    import sc_runner
    original = dict(sc_runner.__dict__)
    try:
        sc_runner.write_sc01_report = lambda r, o: {"text": "satu"}
        sc_runner.write_sc02_report = lambda r, o: {"text": "dua"}
        assert list(run_reports([], Path("."), ["sc02"])) == ["sc02"]
    finally:
        for key in ("write_sc01_report", "write_sc02_report"):
            sc_runner.__dict__[key] = original[key]


def test_every_available_criterion_has_a_report_builder():
    """Kriteria baru tanpa builder akan gagal jelas, bukan hilang diam-diam.

    Sebelumnya test ini membandingkan dengan tuple hardcoded ("sc01", "sc02"),
    sehingga ia justru harus disunting setiap kali kriteria bertambah dan tidak
    pernah benar-benar memeriksa `run_reports`. Sekarang yang diperiksa adalah
    kemampuan runner melaporkan kriteria itu, bukan daftar yang ditulis tangan.
    """
    import sc_runner

    for name in AVAILABLE_CRITERIA:
        # Builder harus ada sebagai fungsi bernama, dan run_reports harus
        # benar-benar memanggilnya untuk kriteria ini.
        assert hasattr(sc_runner, f"write_{name}_report"), (
            f"{name} belum punya fungsi write_{name}_report"
        )
        called_names = []
        original = getattr(sc_runner, f"write_{name}_report")
        try:
            setattr(sc_runner, f"write_{name}_report",
                    lambda r, o: called_names.append(1) or {"text": ""})
            result = sc_runner.run_reports([], Path("."), [name])
            assert name in result, f"{name} tidak dilaporkan oleh run_reports"
            assert called_names, f"builder {name} tidak pernah dipanggil"
        finally:
            setattr(sc_runner, f"write_{name}_report", original)
