"""SC-04 di dalam runner: biaya diturunkan, bukan dibaca dari berkas.

Yang dikunci:
1. `--sc04` berdiri sendiri tanpa memanggil model.
2. Biaya dihitung dari token dengan tarif yang berlaku sekarang.
3. Mengubah tarif atau kurs mengubah laporan tanpa mengukur ulang.
4. Tanpa sampel, laporan bilang belum diukur.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc04_cost as sc04  # noqa: E402
import sc_runner  # noqa: E402


SAMPLES = """file,ok,error,prompt_tokens,completion_tokens
a.jpg,True,,1000,1000
b.jpg,True,,2000,500
"""


def tulis_sampel(out: Path, isi: str = SAMPLES) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "sc04_samples.csv").write_text(isi, encoding="utf-8")


@pytest.fixture(autouse=True)
def env_bersih(monkeypatch):
    monkeypatch.setattr(sc04, "PRICE_PROMPT_USD", 1e-6)
    monkeypatch.setattr(sc04, "PRICE_COMPLETION_USD", 2e-6)
    monkeypatch.setattr(sc04, "USD_TO_IDR", 10000.0)
    monkeypatch.setattr(sc04, "TARGET_IDR", 50.0)
    for nama in (sc04.ENV_PROMPT, sc04.ENV_COMPLETION, sc04.ENV_USD_IDR,
                 sc04.ENV_TARGET):
        monkeypatch.delenv(nama, raising=False)


# --------------------------------------------- tanpa sampel

def test_missing_samples_reports_not_measured(tmp_path):
    hasil = sc_runner.write_sc04_report([], tmp_path)
    teks = (tmp_path / "sc04_report.txt").read_text(encoding="utf-8")
    assert "BELUM DIUKUR" in teks
    assert hasil["result"] is None


def test_missing_samples_explains_the_harness(tmp_path):
    sc_runner.write_sc04_report([], tmp_path)
    teks = (tmp_path / "sc04_report.txt").read_text(encoding="utf-8")
    assert "_sc04_run.py" in teks


def test_missing_exchange_rate_is_refused_not_guessed(tmp_path, monkeypatch):
    """Kurs tidak ditebak: tanpa kurs, jangan laporkan angka apa pun."""
    monkeypatch.setattr(sc04, "USD_TO_IDR", 0.0)
    tulis_sampel(tmp_path)
    hasil = sc_runner.write_sc04_report([], tmp_path)
    teks = (tmp_path / "sc04_report.txt").read_text(encoding="utf-8")
    assert hasil["result"] is None
    assert "BELUM DIUKUR" in teks
    assert "Kurs belum diisi" in teks


# --------------------------------------------- dengan sampel

def test_cost_is_computed_from_tokens(tmp_path):
    tulis_sampel(tmp_path)
    c = sc_runner.write_sc04_report([], tmp_path)["result"]
    # a: (1000*1e-6 + 1000*2e-6) * 10000 = Rp30
    # b: (2000*1e-6 +  500*2e-6) * 10000 = Rp30
    assert c["measured"] == 2
    assert c["mean_idr"] == pytest.approx(30.0)


def test_changing_the_tariff_changes_the_report(tmp_path, monkeypatch):
    """Inti penyesuaian tarif: tanpa mengukur ulang, laporan ikut berubah."""
    tulis_sampel(tmp_path)
    a = sc_runner.write_sc04_report([], tmp_path)["result"]["mean_idr"]

    monkeypatch.setattr(sc04, "PRICE_PROMPT_USD", 3e-6)
    monkeypatch.setattr(sc04, "PRICE_COMPLETION_USD", 4e-6)
    b = sc_runner.write_sc04_report([], tmp_path)["result"]["mean_idr"]

    assert b > a


def test_changing_the_exchange_rate_changes_the_report(tmp_path, monkeypatch):
    tulis_sampel(tmp_path)
    a = sc_runner.write_sc04_report([], tmp_path)["result"]["mean_idr"]

    monkeypatch.setattr(sc04, "USD_TO_IDR", 20000.0)
    b = sc_runner.write_sc04_report([], tmp_path)["result"]["mean_idr"]

    assert b == pytest.approx(a * 2)


def test_csv_holding_a_stale_cost_column_is_ignored(tmp_path):
    """Kalau CSV pernah menyimpan biaya, kolom itu tidak boleh dipercaya.

    Biaya adalah turunan, bukan fakta. Berkas lama yang masih membawa kolom
    `cost_idr` harus diabaikan, bukan dipakai.
    """
    isi = ("file,ok,error,prompt_tokens,completion_tokens,cost_idr\n"
           "a.jpg,True,,1000,1000,999999\n")
    tulis_sampel(tmp_path, isi)
    c = sc_runner.write_sc04_report([], tmp_path)["result"]
    # (1000*1e-6 + 1000*2e-6) * 10000 = Rp30, bukan Rp999.999
    assert c["mean_idr"] == pytest.approx(30.0)


def test_report_writes_both_files(tmp_path):
    tulis_sampel(tmp_path)
    sc_runner.write_sc04_report([], tmp_path)
    assert (tmp_path / "sc04_report.txt").exists()
    data = json.loads((tmp_path / "sc04_metrics.json").read_text(encoding="utf-8"))
    assert "mean_idr" in data
    assert "pricing" in data


def test_failed_rows_are_excluded(tmp_path):
    isi = SAMPLES + "c.jpg,False,APIError,0,0\n"
    tulis_sampel(tmp_path, isi)
    c = sc_runner.write_sc04_report([], tmp_path)["result"]
    assert c["measured"] == 2
    assert c["failed"] == 1


# --------------------------------------------- pemilihan kriteria

def test_sc04_is_a_peer_of_the_other_criteria():
    assert "sc04" in sc_runner.AVAILABLE_CRITERIA


def test_sc04_alone_is_selected_by_its_own_flag():
    class A:
        all = False
        sc01 = False
        sc02 = False
        sc03 = False
        sc04 = True

    assert sc_runner.selected_criteria(A()) == ["sc04"]


def test_bare_command_includes_sc04():
    class A:
        all = False
        sc01 = False
        sc02 = False
        sc03 = False
        sc04 = False

    assert "sc04" in sc_runner.selected_criteria(A())
