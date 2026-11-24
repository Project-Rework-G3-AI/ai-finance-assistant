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
