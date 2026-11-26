"""SC-06 di dalam runner: merangkum sampel, gratis, tanpa dataset.

Yang dikunci:
1. `--sc06` tidak menuntut kunci AI maupun dataset gambar. Pemanggilan model
   dilakukan `_sc06_run.py`; runner hanya merangkum sampel yang sudah ada.
2. Tanpa sampel, laporannya bilang belum diukur beserta perintahnya.
3. `--sc06` tidak mencetak banner "hasil lama dipakai lagi", karena ia tidak
   membaca keluaran ekstraksi.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc_runner  # noqa: E402


def test_sc06_is_a_peer_of_the_other_criteria():
    assert "sc06" in sc_runner.AVAILABLE_CRITERIA


def test_sc06_summarising_needs_no_credentials(monkeypatch, tmp_path):
    """Merangkum sampel tidak boleh menuntut kunci model atau dataset.

    Pemanggilan model ada di `_sc06_run.py`. Kalau runner ikut menuntut kunci,
    pengguna yang hanya ingin melihat laporan dari sampel lama jadi terhalang.
    """
    for var in ("AI_API_KEY", "GOOGLE_OAUTH_REFRESH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SC_PAIRS", str(tmp_path / "tidak-ada.csv"))
    monkeypatch.setenv("SC_IMAGES", str(tmp_path / "tidak-ada"))

    assert "sc06" in sc_runner.FREE_CRITERIA

    hasil = sc_runner.write_sc06_report([], tmp_path)
    assert hasil["result"] is None
    assert "BELUM DIUKUR" in hasil["text"]
    # Laporan harus menyebut perintah yang harus dijalankan lebih dulu.
    assert "_sc06_run.py" in hasil["text"]


def test_sc06_reports_belum_diukur_without_samples(tmp_path):
    """Tanpa sampel: belum diukur, bukan crash dan bukan hijau."""
    hasil = sc_runner.write_sc06_report([], tmp_path)
    assert hasil["result"] is None
    assert "BELUM DIUKUR" in hasil["text"]
    assert (tmp_path / "sc06_report.txt").is_file()


def test_sc06_does_not_print_the_reuse_banner():
    """SC-06 tidak membaca hasil ekstraksi, jadi tidak boleh mengaku reuse."""
    import inspect

    sumber = inspect.getsource(sc_runner.write_sc06_report)
    assert "hasil lama" not in sumber.lower()
    assert "source.json" not in sumber
