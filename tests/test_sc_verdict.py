"""Angka mana yang dibandingkan dengan target, pada kedua kriteria.

Kedua laporan menampilkan beberapa angka sekaligus. Tanpa menyebut mana yang
dinilai, baris "Status: BELUM TERCAPAI" tidak bisa ditafsirkan dan pembaca bisa
menyimpulkan laporan yang salah. Test ini mengunci aturan yang berlaku untuk
SC-01 dan SC-02 sekaligus, karena keduanya pernah punya cacat yang sama.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sc_runner import verdict_block  # noqa: E402


# ------------------------------------------------------------- blok keputusan

def test_block_names_the_judged_number_and_its_value():
    teks = "\n".join(verdict_block("akurasi", 0.046, 0.85, []))
    assert "Angka yang dinilai : akurasi 4.6%" in teks
    assert "dibandingkan dengan target" in teks


def test_block_states_the_target():
    teks = "\n".join(verdict_block("akurasi", 0.5, 0.85, []))
    assert "minimal 85%" in teks


def test_block_marks_failure_below_target():
    teks = "\n".join(verdict_block("akurasi", 0.849, 0.85, []))
    assert "BELUM TERCAPAI" in teks


def test_block_marks_success_at_exactly_the_target():
    """Tepat di target dihitung tercapai, bukan gagal karena pembulatan."""
    teks = "\n".join(verdict_block("akurasi", 0.85, 0.85, []))
    assert "TERCAPAI" in teks
    assert "BELUM" not in teks


def test_block_lists_other_numbers_with_a_reason():
    teks = "\n".join(verdict_block(
        "akurasi", 0.5, 0.85,
        [("baseline", 0.754, "batas bawah")]))
    assert "Angka lain" in teks
    assert "baseline" in teks
    assert "75.4%" in teks
    assert "batas bawah" in teks


def test_block_says_plainly_that_other_numbers_are_not_judged():
    teks = "\n".join(verdict_block("akurasi", 0.5, 0.85, []))
    assert "tidak dipakai menilai target" in teks


# ------------------------------------------------------------------- SC-01

def sc01_report(tmp_path, pairs):
    import sc_runner
    tmp_path.mkdir(parents=True, exist_ok=True)
    rows = [{"file": f"f{i}.jpg", "reference_category": ref,
             "proposed_category": prop}
            for i, (ref, prop) in enumerate(pairs)]
    return sc_runner.write_report(rows, tmp_path)["text"]


def test_sc01_report_names_accuracy_as_the_judged_number(tmp_path):
    teks = sc01_report(tmp_path, [("A", "A"), ("B", "C")])
    assert "Angka yang dinilai : akurasi" in teks


def test_sc01_report_shows_baseline_and_macro_as_not_judged(tmp_path):
    """Baseline dan macro-average tampil, tapi bukan penentu status."""
    teks = sc01_report(tmp_path, [("A", "A"), ("A", "B"), ("B", "C")])
    assert "baseline kelas mayoritas" in teks
    assert "macro-average recall" in teks
    assert teks.count("tidak dipakai menilai target") >= 1


def test_sc01_status_follows_accuracy_not_baseline(tmp_path):
    """Model yang selalu menebak kelas mayoritas gagal walau baseline tinggi.

    Tiga baris, dua di antaranya kelas mayoritas. Menebak mayoritas terus
    memberi akurasi 66,7% dan baseline 66,7%, jadi lift nol. Target 85% tidak
    tercapai, dan status harus mengikuti akurasi.
    """
    teks = sc01_report(tmp_path, [("A", "A"), ("A", "A"), ("B", "A")])
    assert "BELUM TERCAPAI" in teks


def test_sc01_target_is_85_percent(tmp_path):
    teks = sc01_report(tmp_path, [("A", "A")])
    assert "minimal 85%" in teks


# ------------------------------------------------------------------- SC-02

def sc02_report(tmp_path, category="Bahan Baku"):
    import sc_runner
    tmp_path.mkdir(parents=True, exist_ok=True)
    rows = [{
        "file": "a",
        "record": {"date": "2026-01-01", "amount": 1000, "bank": "BNI",
                   "direction": "keluar", "category": category,
                   "remark": "", "mode": "vision"},
        "reference": {"date": "2026-01-01", "amount": "1000", "bank": "BNI",
                      "direction": "", "category": "Bahan Baku"},
    }]
    return sc_runner.write_sc02_report(rows, tmp_path)["text"]


def test_sc02_report_names_the_judged_number(tmp_path):
    teks = sc02_report(tmp_path)
    assert "Angka yang dinilai : kecocokan rata-rata" in teks


def test_sc02_report_states_the_denominator(tmp_path):
    teks = sc02_report(tmp_path)
    assert "4 field beracuan" in teks


def test_sc02_report_shows_completeness_as_not_judged(tmp_path):
    teks = sc02_report(tmp_path)
    assert "kelengkapan rata-rata" in teks
    assert "belum tentu benar" in teks


def test_sc02_target_is_90_percent(tmp_path):
    teks = sc02_report(tmp_path)
    assert "minimal 90%" in teks


def test_sc02_wrong_category_fails_the_target(tmp_path):
    """Kategori salah menurunkan kecocokan, jadi status harus gagal."""
    teks = sc02_report(tmp_path, category="SALAH")
    assert "BELUM TERCAPAI" in teks


# ------------------------------------------------------------ konsistensi

def test_both_criteria_use_the_same_verdict_wording(tmp_path):
    """Satu sumber teks, supaya kedua laporan tidak bisa berbeda gaya."""
    sc01 = sc01_report(tmp_path / "a", [("A", "A")])
    sc02 = sc02_report(tmp_path / "b")
    for teks in (sc01, sc02):
        assert "Angka yang dinilai" in teks
        assert "dibandingkan dengan target" in teks
        assert "Angka lain (tidak dipakai menilai target)" in teks


def test_no_report_leaves_status_without_naming_the_number(tmp_path):
    """Cacat lama: status muncul tanpa menyebut angka yang dinilai."""
    for teks in (sc01_report(tmp_path / "a", [("A", "A")]),
                 sc02_report(tmp_path / "b")):
        i_status = teks.index("Status")
        i_angka = teks.index("Angka yang dinilai")
        assert i_angka < i_status, "angka yang dinilai harus disebut sebelum status"
