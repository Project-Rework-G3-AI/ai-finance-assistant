"""Aturan SC-04: biaya diturunkan dari variabel perhitungan, bukan dipatok.

Yang dikunci di sini adalah **cara menghitung**, bukan angkanya. Angka berubah
setiap kali tarif atau kurs berubah; aturannya tidak boleh ikut berubah diam-diam.

Fokus utama: memastikan variabel perhitungan (tarif, kurs, target) benar-benar
menentukan hasil, dan bahwa hasil hitung tidak pernah tersimpan sehingga tidak
bisa basi.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc04_cost as sc04  # noqa: E402


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    """Env dari mesin tidak boleh bocor ke test; tiap test mengatur sendiri."""
    for name in (sc04.ENV_PROMPT, sc04.ENV_COMPLETION, sc04.ENV_USD_IDR,
                 sc04.ENV_TARGET, sc04.ENV_MODEL):
        monkeypatch.delenv(name, raising=False)


def price(prompt=1e-6, completion=2e-6, model="test/model"):
    return sc04.Pricing(model=model, prompt_usd=prompt,
                        completion_usd=completion, source="test")


def sample(file="a.jpg", prompt=1000, completion=500, ok=True):
    return sc04.Sample(file=file, ok=ok, prompt_tokens=prompt,
                       completion_tokens=completion)


# ------------------------------------------------------- rumus biaya

def test_cost_is_prompt_plus_completion_times_rate():
    """Rumus dasar: dua komponen token, bukan satu."""
    p = price(prompt=2e-6, completion=5e-6)
    # 1000 x 2e-6 = 0.002 ; 500 x 5e-6 = 0.0025 -> 0.0045 USD
    assert p.cost_usd(1000, 500) == pytest.approx(0.0045)


def test_cost_in_idr_multiplies_by_the_exchange_rate():
    p = price(prompt=1e-6, completion=0.0)
    assert sc04.cost_idr(p, 1000, 0, 18000) == pytest.approx(18.0)


def test_prompt_and_completion_have_different_rates():
    """Tarif completion tidak boleh diabaikan.

    Token sengaja dibuat berbeda (1000 vs 100) supaya menukar tarif terlihat.
    Dengan jumlah token yang sama, menukar dua tarif menghasilkan angka identik
    dan test-nya tidak membuktikan apa pun.
    """
    a = sc04.cost_idr(price(prompt=1e-6, completion=9e-6), 1000, 100, 1)
    b = sc04.cost_idr(price(prompt=9e-6, completion=1e-6), 1000, 100, 1)
    assert a != b
    # a = 1000e-6 + 900e-6 = 0.0019 ; b = 9000e-6 + 100e-6 = 0.0091
    assert a == pytest.approx(0.0019)
    assert b == pytest.approx(0.0091)


# ------------------------------------------------------- penyesuaian tarif

def test_cli_price_overrides_everything():
    p = sc04.pricing_from(prompt=3e-6, completion=4e-6,
                          catalog={"id": "katalog", "pricing": {"prompt": "1e-9",
                                                                "completion": "1e-9"}})
    assert p.prompt_usd == pytest.approx(3e-6)
    assert p.completion_usd == pytest.approx(4e-6)
    assert "CLI" in p.source


def test_env_price_overrides_the_catalog(monkeypatch):
    monkeypatch.setenv(sc04.ENV_PROMPT, "5e-6")
    monkeypatch.setenv(sc04.ENV_COMPLETION, "6e-6")
    p = sc04.pricing_from(catalog={"id": "katalog",
                                   "pricing": {"prompt": "1e-9", "completion": "1e-9"}})
    assert p.prompt_usd == pytest.approx(5e-6)
    assert "lingkungan" in p.source


def test_code_variable_overrides_the_catalog(monkeypatch):
    """Variabel di kode harus mengalahkan katalog, tapi kalah dari env."""
    monkeypatch.setattr(sc04, "PRICE_PROMPT_USD", 7e-6)
    monkeypatch.setattr(sc04, "PRICE_COMPLETION_USD", 8e-6)
    p = sc04.pricing_from(catalog={"id": "katalog",
                                   "pricing": {"prompt": "1e-9", "completion": "1e-9"}})
    assert p.prompt_usd == pytest.approx(7e-6)
    assert "sc04_cost" in p.source


def test_env_beats_the_code_variable(monkeypatch):
    monkeypatch.setattr(sc04, "PRICE_PROMPT_USD", 7e-6)
    monkeypatch.setattr(sc04, "PRICE_COMPLETION_USD", 8e-6)
    monkeypatch.setenv(sc04.ENV_PROMPT, "1e-6")
    monkeypatch.setenv(sc04.ENV_COMPLETION, "2e-6")
    p = sc04.pricing_from()
    assert p.prompt_usd == pytest.approx(1e-6)


def test_catalog_is_used_when_nothing_is_filled(monkeypatch):
    monkeypatch.setattr(sc04, "PRICE_PROMPT_USD", 0.0)
    monkeypatch.setattr(sc04, "PRICE_COMPLETION_USD", 0.0)
    p = sc04.pricing_from(catalog={"id": "m", "pricing": {"prompt": "1.5e-7",
                                                          "completion": "6e-7"}})
    assert p.prompt_usd == pytest.approx(1.5e-7)
    assert "katalog" in p.source


def test_half_a_rate_is_refused():
    """Setengah tarif berarti mencampur sumber; itu harus ditolak, bukan ditebak."""
    with pytest.raises(SystemExit):
        sc04.pricing_from(prompt=1e-6, completion=None)


def test_no_rate_at_all_is_refused(monkeypatch):
    """Bila tarif di kode dikosongkan dan katalog tidak ada, berhenti.

    Tarif bawaan di kode terisi, jadi kasus ini hanya terjadi bila seseorang
    mengosongkannya dengan sengaja tanpa memberi sumber lain.
    """
    monkeypatch.setattr(sc04, "PRICE_PROMPT_USD", 0.0)
    monkeypatch.setattr(sc04, "PRICE_COMPLETION_USD", 0.0)
    with pytest.raises(SystemExit):
        sc04.pricing_from()


# ------------------------------------------------------- penyesuaian kurs

def test_cli_exchange_rate_wins(monkeypatch):
    monkeypatch.setenv(sc04.ENV_USD_IDR, "17000")
    assert sc04.usd_to_idr_from(20000) == pytest.approx(20000)


def test_env_exchange_rate_used(monkeypatch):
    monkeypatch.setenv(sc04.ENV_USD_IDR, "17000")
    assert sc04.usd_to_idr_from() == pytest.approx(17000)


def test_code_exchange_rate_used(monkeypatch):
    monkeypatch.setattr(sc04, "USD_TO_IDR", 16500)
    assert sc04.usd_to_idr_from() == pytest.approx(16500)


def test_missing_exchange_rate_is_zero_not_a_guess(monkeypatch):
    """Kurs tidak ditebak: 0 dipakai pemanggil sebagai tanda wajib diisi."""
    monkeypatch.setattr(sc04, "USD_TO_IDR", 0.0)
    assert sc04.usd_to_idr_from() == 0.0


def test_bad_exchange_rate_is_refused(monkeypatch):
    monkeypatch.setenv(sc04.ENV_USD_IDR, "not-a-number")
    with pytest.raises(SystemExit):
        sc04.usd_to_idr_from()


# ------------------------------------------------------- penyesuaian target

def test_target_defaults_to_the_brd_figure():
    assert sc04.target_from() == pytest.approx(50.0)


def test_target_can_come_from_env(monkeypatch):
    monkeypatch.setenv(sc04.ENV_TARGET, "40")
    assert sc04.target_from() == pytest.approx(40.0)


def test_target_can_come_from_code(monkeypatch):
    monkeypatch.setattr(sc04, "TARGET_IDR", 35.0)
    assert sc04.target_from() == pytest.approx(35.0)


def test_cli_target_beats_env(monkeypatch):
    monkeypatch.setenv(sc04.ENV_TARGET, "40")
    assert sc04.target_from(30) == pytest.approx(30.0)


# ------------------------------------------------------- penilaian

def test_pass_when_mean_is_below_target():
    c = sc04.compute([sample(prompt=1000, completion=0)],
                     target=50, pricing=price(prompt=1e-6, completion=0),
                     usd_to_idr=10000)
    # 1000 x 1e-6 x 10000 = Rp10
    assert c["mean_idr"] == pytest.approx(10.0)
    assert c["pass"] is True
    assert sc04.verdict(c) == "TERCAPAI"


def test_fail_when_mean_is_above_target():
    c = sc04.compute([sample(prompt=10000, completion=0)],
                     target=50, pricing=price(prompt=1e-6, completion=0),
                     usd_to_idr=10000)
    assert c["pass"] is False
    assert sc04.verdict(c) == "BELUM TERCAPAI"


def test_exactly_at_target_counts_as_pass():
    c = sc04.compute([sample(prompt=5000, completion=0)],
                     target=50, pricing=price(prompt=1e-6, completion=0),
                     usd_to_idr=10000)
    assert c["mean_idr"] == pytest.approx(50.0)
    assert c["pass"] is True


def test_no_samples_never_reports_pass():
    c = sc04.compute([], target=50)
    assert c["measured"] == 0
    assert c["pass"] is False
    assert sc04.verdict(c) == "BELUM DIUKUR"


def test_failed_samples_do_not_enter_the_average():
    """Gambar gagal bukan biaya Rp0; itu tidak ada data."""
    ok = sample(file="a.jpg", prompt=1000, completion=0)
    ok.cost_idr = 10.0
    failed = sample(file="b.jpg", ok=False)
    failed.cost_idr = 0.0
    c = sc04.compute([ok, failed], target=50)
    assert c["measured"] == 1
    assert c["failed"] == 1
    assert c["mean_idr"] == pytest.approx(10.0)


def test_over_target_counts_per_image_not_just_the_mean():
    """Rata-rata bisa lulus meski sebagian gambar mahal; itu harus terlihat."""
    cheapest = sample(file="a.jpg")
    cheapest.cost_idr = 5.0
    expensive = sample(file="b.jpg")
    expensive.cost_idr = 500.0
    c = sc04.compute([cheapest, expensive], target=50)
    assert c["over_target"] == 1


# ------------------------------------------------------- tarif model

def test_tariff_is_one_editable_block_for_the_one_model_we_use():
    """Kita memakai satu model, jadi tarifnya satu blok, bukan tabel.

    Ini yang disunting saat harga penyedia berubah. Kalau nilainya nol, tarif
    diambil dari katalog supaya tidak ada tebakan.
    """
    assert sc04.PRICE_PROMPT_USD > 0
    assert sc04.PRICE_COMPLETION_USD > 0
    p = sc04.pricing_from(model="deepseek/deepseek-v4.1-flash-1017",
                          catalog={"id": "x", "pricing": {"prompt": "9e-9",
                                                          "completion": "9e-9"}})
    assert p.prompt_usd == pytest.approx(sc04.PRICE_PROMPT_USD)
    assert "PRICE_" in p.source


def test_editing_the_tariff_changes_the_cost(monkeypatch):
    """Mengubah tarif di kode harus mengubah biaya yang dilaporkan."""
    s = sample(prompt=1000, completion=0)
    monkeypatch.setattr(sc04, "PRICE_PROMPT_USD", 1e-6)
    a = sc04.compute([s], target=50, pricing=price(prompt=1e-6, completion=0),
                     usd_to_idr=10000)["mean_idr"]
    monkeypatch.setattr(sc04, "PRICE_PROMPT_USD", 3e-6)
    b = sc04.compute([s], target=50, pricing=price(prompt=3e-6, completion=0),
                     usd_to_idr=10000)["mean_idr"]
    assert b == pytest.approx(a * 3)


def test_zero_tariff_falls_back_to_the_catalog(monkeypatch):
    """Tarif nol berarti belum diisi; jangan menebak, ambil dari katalog."""
    monkeypatch.setattr(sc04, "PRICE_PROMPT_USD", 0.0)
    monkeypatch.setattr(sc04, "PRICE_COMPLETION_USD", 0.0)
    p = sc04.pricing_from(model="m", catalog={"id": "m",
                                             "pricing": {"prompt": "2e-6",
                                                         "completion": "3e-6"}})
    assert p.prompt_usd == pytest.approx(2e-6)
    assert "katalog" in p.source


# ------------------------------------------------------- laporan

def test_report_names_the_judged_number_before_the_status():
    c = sc04.compute([sample(prompt=1000, completion=0)], target=50,
                     pricing=price(prompt=1e-6, completion=0), usd_to_idr=10000)
    text = sc04.report(c)
    assert text.index("Angka yang dinilai") < text.index("Status")
    assert "per gambar" in text


def test_report_states_target_and_rate_source():
    c = sc04.compute([sample(prompt=1000, completion=0)], target=50,
                     pricing=price(prompt=1e-6, completion=0), usd_to_idr=10000)
    text = sc04.report(c)
    assert "Rp50.00" in text
    assert "sumber tarif" in text
    assert "kurs" in text


def test_report_shows_tokens_so_the_cost_can_be_rechecked():
    """Tanpa token, pembaca tidak bisa memverifikasi biaya sendiri."""
    c = sc04.compute([sample(prompt=1000, completion=500)], target=50,
                     pricing=price(), usd_to_idr=10000)
    text = sc04.report(c)
    assert "prompt" in text
    assert "completion" in text
    assert "1000" in text


def test_report_says_not_measured_without_samples():
    text = sc04.report(sc04.compute([]))
    assert "BELUM DIUKUR" in text
    assert "_sc04_run.py" in text


def test_write_report_creates_both_files(tmp_path):
    c = sc04.compute([sample(prompt=1000, completion=0)], target=50,
                     pricing=price(), usd_to_idr=10000)
    sc04.write_report(c, tmp_path)
    assert (tmp_path / "sc04_report.txt").exists()
    data = json.loads((tmp_path / "sc04_metrics.json").read_text(encoding="utf-8"))
    assert "mean_idr" in data


# ------------------------------------------------------- biaya tidak boleh basi

def test_compute_recomputes_cost_from_tokens_and_current_rate():
    """Inti penyesuaian: biaya adalah turunan, bukan angka tersimpan.

    Token yang sama, tarif berbeda -> biaya harus berbeda. Kalau biaya pernah
    disimpan di CSV dan dipakai ulang, test ini akan gagal.
    """
    s = sample(prompt=1000, completion=0)
    cheapest = sc04.compute([s], target=50, pricing=price(prompt=1e-6, completion=0),
                         usd_to_idr=10000)["mean_idr"]
    expensive = sc04.compute([s], target=50, pricing=price(prompt=2e-6, completion=0),
                         usd_to_idr=10000)["mean_idr"]
    assert expensive == pytest.approx(cheapest * 2)


def test_compute_recomputes_cost_from_tokens_and_current_exchange_rate():
    s = sample(prompt=1000, completion=0)
    a = sc04.compute([s], target=50, pricing=price(prompt=1e-6, completion=0),
                     usd_to_idr=10000)["mean_idr"]
    b = sc04.compute([s], target=50, pricing=price(prompt=1e-6, completion=0),
                     usd_to_idr=20000)["mean_idr"]
    assert b == pytest.approx(a * 2)
