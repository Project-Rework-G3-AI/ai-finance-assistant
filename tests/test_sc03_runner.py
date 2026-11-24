"""SC-03 di dalam runner: berbeda sifat dari SC-01 dan SC-02.

Waktu tidak tersimpan di hasil ekstraksi, jadi SC-03 tidak bisa dihitung ulang
dari `results_per_row.csv`. Test ini mengunci tiga hal:

1. `--sc03` berdiri sendiri tanpa menuntut kunci model.
2. `--sc03` tidak membaca hasil ekstraksi.
3. Tanpa sampel waktu, laporan bilang belum diukur alih-alih mengarang angka.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc_runner  # noqa: E402


SAMPLES = """file,ok,error,status,row,extract,dedupe,upload,append,reply,stored,replied
a.jpg,True,,ok,2,3.0,1.0,0.0,0.5,0.0,4.5,4.5
b.jpg,True,,ok,3,7.0,1.0,0.0,0.5,0.0,8.5,8.5
"""


def tulis_sampel(out: Path, isi: str = SAMPLES) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "sc03_samples.csv").write_text(isi, encoding="utf-8")


# --------------------------------------------- tanpa sampel

def test_missing_samples_reports_not_measured(tmp_path):
    """Tanpa sampel, laporan harus bilang belum diukur, bukan menebak."""
    hasil = sc_runner.write_sc03_report([], tmp_path)
    teks = (tmp_path / "sc03_report.txt").read_text(encoding="utf-8")
    assert "BELUM DIUKUR" in teks
    assert hasil["result"] is None


def test_missing_samples_explains_why_and_how(tmp_path):
    """Pembaca harus tahu kenapa tidak bisa dihitung dan apa yang harus dilakukan."""
    sc_runner.write_sc03_report([], tmp_path)
    teks = (tmp_path / "sc03_report.txt").read_text(encoding="utf-8")
    assert "tidak bisa dihitung ulang" in teks
    assert "_sc03_run.py" in teks


# --------------------------------------------- dengan sampel

def test_report_uses_the_samples_on_disk(tmp_path):
    tulis_sampel(tmp_path)
    hasil = sc_runner.write_sc03_report([], tmp_path)
    c = hasil["result"]
    assert c["measured"] == 2
    # rata-rata (4.5 + 8.5) / 2 = 6.5 -> di atas target 5 detik
    assert c["mean_stored"] == pytest.approx(6.5)
    assert c["pass"] is False


def test_report_writes_both_output_files(tmp_path):
    tulis_sampel(tmp_path)
    sc_runner.write_sc03_report([], tmp_path)
    assert (tmp_path / "sc03_report.txt").exists()
    assert (tmp_path / "sc03_metrics.json").exists()


def test_metrics_json_contains_the_judged_number(tmp_path):
    """Angka yang dipakai menilai harus bisa diperiksa ulang dari JSON."""
    tulis_sampel(tmp_path)
    sc_runner.write_sc03_report([], tmp_path)
    c = json.loads((tmp_path / "sc03_metrics.json").read_text(encoding="utf-8"))
    assert "mean_stored" in c
    assert "stored" in c
    assert "stages" in c


def test_failed_rows_are_excluded_from_the_average(tmp_path):
    isi = SAMPLES + 'c.jpg,False,APIError,,0,0,0,0,0,0,0,0\n'
    tulis_sampel(tmp_path, isi)
    hasil = sc_runner.write_sc03_report([], tmp_path)
    c = hasil["result"]
    assert c["measured"] == 2
    assert c["failed"] == 1
    assert c["mean_stored"] == pytest.approx(6.5)


def test_report_does_not_claim_reply_was_measured(tmp_path):
    """Harness me-mock Telegram, jadi reply tidak boleh dilaporkan sebagai angka."""
    tulis_sampel(tmp_path)
    sc_runner.write_sc03_report([], tmp_path)
    teks = (tmp_path / "sc03_report.txt").read_text(encoding="utf-8")
    assert "tidak diukur" in teks


# --------------------------------------------- pemilihan kriteria

def test_sc03_is_a_peer_of_the_other_criteria():
    assert "sc03" in sc_runner.AVAILABLE_CRITERIA
    assert sc_runner.AVAILABLE_CRITERIA[0] == "sc01"


def test_sc03_alone_is_selected_by_its_own_flag():
    class A:
        all = False
        sc01 = False
        sc02 = False
        sc03 = True

    assert sc_runner.selected_criteria(A()) == ["sc03"]


def test_bare_command_includes_sc03():
    """Tanpa flag berarti semua, termasuk SC-03."""
    class A:
        all = False
        sc01 = False
        sc02 = False
        sc03 = False

    assert "sc03" in sc_runner.selected_criteria(A())
