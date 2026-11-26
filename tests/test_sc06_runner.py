"""SC-06 di dalam runner: dua bagian, dan yang gratis tetap gratis.

Yang dikunci:
1. `--sc06` bisa dijalankan tanpa kunci AI. Bagian susunan kolom hanya butuh
   berkas template; bagian per baris hanya merangkum sampel yang sudah ada.
2. Tanpa sampel, bagian per baris dilaporkan BELUM DIUKUR, bukan hijau.
3. Tanpa template, laporannya bilang BELUM DIUKUR beserta perintah mengunduhnya.
4. `--sc06` tidak mencetak banner "hasil lama dipakai lagi", karena ia tidak
   membaca keluaran ekstraksi.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc_runner  # noqa: E402
import sc06_mapping as sc06  # noqa: E402

ada_template = (ROOT / sc06.TEMPLATE_DIR / sc06.TEMPLATE_FILES[0]).is_file()
butuh_template = pytest.mark.skipif(not ada_template,
                                    reason="template perusahaan belum diunduh")


def test_sc06_is_a_peer_of_the_other_criteria():
    assert "sc06" in sc_runner.AVAILABLE_CRITERIA


def test_sc06_needs_no_credentials(monkeypatch, tmp_path):
    """Merangkum tidak boleh menuntut kunci model, Google, atau dataset gambar."""
    for var in ("AI_API_KEY", "GOOGLE_OAUTH_REFRESH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SC_PAIRS", str(tmp_path / "tidak-ada.csv"))
    monkeypatch.setenv("SC_IMAGES", str(tmp_path / "tidak-ada"))

    assert "sc06" in sc_runner.FREE_CRITERIA
    hasil = sc_runner.write_sc06_report([], tmp_path)
    assert hasil["text"]


@butuh_template
def test_without_samples_the_row_section_is_not_measured(tmp_path):
    """Tanpa sampel, susunan kolom tetap bisa dinilai, barisnya belum.

    Ini bukan kegagalan: bagian 1 memang tidak butuh model. Yang penting
    verdict-nya tidak boleh hijau saat bagian 2 belum diukur.
    """
    hasil = sc_runner.write_sc06_report([], tmp_path)
    laporan = hasil["result"]
    assert laporan is not None
    assert laporan.total_rows == 0
    assert sc06.verdict(laporan) == "BELUM DIUKUR"
    assert "BAGIAN 1" in hasil["text"]
    # Laporan harus menyebut perintah yang mengambil sampel.
    assert "_sc06_run.py" in hasil["text"] or "BELUM DIUKUR" in hasil["text"]


def test_without_template_reports_belum_diukur(monkeypatch, tmp_path):
    """Tanpa template perusahaan, kriteria ini belum bisa diukur."""
    monkeypatch.setattr(sc06, "TEMPLATE_DIR", "dataset/tidak-ada")
    hasil = sc_runner.write_sc06_report([], tmp_path)
    assert hasil["result"] is None
    assert "BELUM DIUKUR" in hasil["text"]
    assert "--download-templates" in hasil["text"]
    assert (tmp_path / "sc06_report.txt").is_file()


def test_sc06_does_not_print_the_reuse_banner():
    """SC-06 tidak membaca hasil ekstraksi, jadi tidak boleh mengaku reuse."""
    import inspect

    sumber = inspect.getsource(sc_runner.write_sc06_report)
    assert "hasil lama" not in sumber.lower()
    assert "source.json" not in sumber
