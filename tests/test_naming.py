"""Penamaan yang dipakai bersama semua kriteria.

Nama yang mengandung `sc01` menyiratkan sesuatu hanya dipakai SC-01. Beberapa
nama memang khusus SC-01 dan itu wajar: `sc01_report.txt`, `write_sc01_report`,
`--sc01`. Yang salah adalah nama yang dipakai bersama tetapi diberi awalan
salah satu kriteria, karena pembaca menyimpulkan cakupannya lebih sempit dari
kenyataan.

Test ini menjaga batas itu: nama bersama tidak boleh berawalan `sc01`, dan
keluaran kedua kriteria harus simetris.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc_common  # noqa: E402
import sc_runner  # noqa: E402


# --------------------------------------------- nama yang dipakai bersama

def test_pair_file_is_not_named_after_one_criterion():
    """Daftar pasangan memasok acuan beberapa kriteria, jadi jangan berawalan sc01."""
    assert "sc01" not in sc_common.PAIRS_SUBDIR.lower()
    assert "sc01" not in sc_common.DEFAULT_PAIRS.lower()


def test_pair_file_is_a_plain_csv_at_the_dataset_root():
    assert sc_common.PAIRS_SUBDIR == "pairs.csv"
    assert sc_common.DEFAULT_PAIRS == "dataset/pairs.csv"


def test_pair_file_name_matches_between_subdir_and_default():
    """Nama berkas di repo dan jalur lokal tidak boleh menyimpang."""
    assert sc_common.PAIRS_SUBDIR.split("/")[-1] == sc_common.DEFAULT_PAIRS.split("/")[-1]


def test_environment_variables_are_not_named_after_one_criterion():
    """SC_PAIRS dan SC_IMAGES dipakai semua kriteria, bukan hanya SC-01."""
    import inspect

    source = inspect.getsource(sc_common)
    for wrong in ("SC01_PAIRS", "SC01_IMAGES", "SC01_RUN_MODEL"):
        assert wrong not in source, f"{wrong} seharusnya SC_*"


# ------------------------------------------------ simetri nama keluaran

def test_report_files_are_symmetric(tmp_path):
    """Kedua kriteria menulis berkas dengan pola nama yang sama."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = [{"file": "a.jpg", "reference_category": "A",
              "proposed_category": "A", "reference_date": "2026-01-01",
              "proposed_date": "2026-01-01", "reference_amount": "1000",
              "proposed_amount": 1000, "proposed_bank": "BNI",
              "proposed_direction": "keluar", "proposed_note": "",
              "mode": "vision", "note": "", "model_note": "", "seconds": 1}]
    sc_runner.write_sc01_report(result, tmp_path)
    sc_runner.write_sc02_report(result, tmp_path)

    created = {p.name for p in tmp_path.iterdir()}
    assert "sc01_report.txt" in created
    assert "sc01_metrics.json" in created
    assert "sc02_report.txt" in created
    assert "sc02_metrics.json" in created


def test_sc01_does_not_write_unsuffixed_output_names(tmp_path):
    """Nama tanpa awalan menyembunyikan bahwa berkas itu milik SC-01 saja."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = [{"file": "a.jpg", "reference_category": "A",
              "proposed_category": "A", "reference_date": "2026-01-01",
              "proposed_date": "2026-01-01", "reference_amount": "1000",
              "proposed_amount": 1000, "proposed_bank": "BNI",
              "proposed_direction": "keluar", "proposed_note": "",
              "mode": "vision", "note": "", "model_note": "", "seconds": 1}]
    sc_runner.write_sc01_report(result, tmp_path)
    created = {p.name for p in tmp_path.iterdir()}
    assert "report.txt" not in created
    assert "metrics.json" not in created


def test_builder_functions_are_named_after_their_criterion():
    assert hasattr(sc_runner, "write_sc01_report")
    assert hasattr(sc_runner, "write_sc02_report")
    assert not hasattr(sc_runner, "write_report"), (
        "write_report tidak menyebut kriteria mana yang dihitung"
    )


# ------------------------------------------ nama yang memang khusus SC-01

def test_criterion_specific_names_are_allowed_to_keep_the_prefix():
    """Yang khusus SC-01 justru harus tetap berawalan sc01."""
    import inspect

    source = inspect.getsource(sc_runner)
    assert "sc01_report.txt" in source
    assert "sc01_metrics.json" in source
