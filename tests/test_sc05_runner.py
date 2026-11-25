"""SC-05 di dalam runner: gratis, tanpa kredensial, dan tidak lewat jalur reuse.

Yang dikunci:
1. `--sc05` bisa dijalankan tanpa kunci AI dan tanpa Google.
2. `--sc05` tidak mencetak banner "hasil lama dipakai lagi", karena ia tidak
   membaca keluaran ekstraksi.
3. Tanpa modul aplikasi, laporannya bilang belum diukur, bukan gagal diam-diam.
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


def test_sc05_is_a_peer_of_the_other_criteria():
    assert "sc05" in sc_runner.AVAILABLE_CRITERIA


def test_sc05_alone_is_selected_by_its_own_flag():
    class A:
        all = False
        sc01 = False
        sc02 = False
        sc03 = False
        sc04 = False
        sc05 = True

    assert sc_runner.selected_criteria(A()) == ["sc05"]


def test_bare_command_includes_sc05():
    class A:
        all = False
        sc01 = False
        sc02 = False
        sc03 = False
        sc04 = False
        sc05 = False

    assert "sc05" in sc_runner.selected_criteria(A())


def test_sc05_report_runs_without_credentials(tmp_path, monkeypatch):
    """Inti sifat SC-05: tidak butuh kunci AI, Google, dataset, atau jaringan."""
    for name in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL",
                 "CASH_REPORT_FOLDER_ID", "CASH_REPORT_TEMPLATE_ID"):
        monkeypatch.delenv(name, raising=False)

    result = sc_runner.write_sc05_report([], tmp_path)
    assert result["result"] is not None, "SC-05 seharusnya bisa jalan tanpa kredensial"
    assert (tmp_path / "sc05_report.txt").exists()


def test_sc05_result_is_written_as_json(tmp_path):
    sc_runner.write_sc05_report([], tmp_path)
    data = json.loads((tmp_path / "sc05_metrics.json").read_text(encoding="utf-8"))
    assert "required_rejected" in data
    assert "required_duplicates" in data
    assert "cases" in data


def test_sc05_reports_every_case(tmp_path):
    result = sc_runner.write_sc05_report([], tmp_path)
    case_item = result["result"]["cases"]
    assert len(case_item) == 3
    name = {k["name"] for k in case_item}
    assert name == {"kirim_ulang_berkas_sama", "isi_sama_file_id_baru",
                    "gambar_berbeda"}


def test_sc05_required_case_rejects_all_duplicates(tmp_path):
    """Kondisi kode saat ini: berkas sama yang dikirim ulang memang ditolak."""
    result = sc_runner.write_sc05_report([], tmp_path)
    c = result["result"]
    assert c["required_duplicates"] == 5
    assert c["required_rejected"] == 5
    assert c["pass"] is True


def test_sc05_reports_the_no_hash_finding(tmp_path):
    """Selisih terhadap BRD harus terlihat, bukan disembunyikan."""
    result = sc_runner.write_sc05_report([], tmp_path)
    c = result["result"]
    assert c["findings_duplicates"] == 5
    assert c["findings_rejected"] == 0
    text = (tmp_path / "sc05_report.txt").read_text(encoding="utf-8")
    assert "Temuan terhadap BRD" in text
    assert "hash" in text


def test_sc05_does_not_read_extraction_results(tmp_path):
    """SC-05 tidak boleh bergantung pada results_per_row.csv.

    Kalau ia membaca berkas itu, menjalankannya di repo bersih akan gagal
    padahal seharusnya bisa jalan tanpa apa pun.
    """
    result = sc_runner.write_sc05_report([], tmp_path)
    assert result["result"]["measured"] == 3
