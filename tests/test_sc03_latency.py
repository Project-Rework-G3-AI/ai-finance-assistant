"""Aturan penilaian SC-03: dua definisi waktu, dan operand yang harus disebut.

Yang dikunci di sini bukan angkanya, melainkan cara menilainya. Angka berubah
setiap run; aturannya tidak boleh ikut berubah diam-diam.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc03_latency as sc03  # noqa: E402


def sample(file="a.jpg", ok=True, **stage):
    s = sc03.Sample(file=file, ok=ok)
    s.stages.update(stage)
    return s


# ------------------------------------------- dua definisi waktu

def test_stored_stops_before_the_telegram_reply():
    """Definisi BRD berhenti di tersimpan, jadi reply tidak ikut dijumlahkan."""
    s = sample(extract=3.0, dedupe=1.0, upload=0.5, append=0.5, reply=9.0)
    assert s.stored == pytest.approx(5.0)


def test_replied_adds_the_telegram_round_trip():
    """Definisi pengguna lebih ketat: menambah perjalanan pulang-pergi."""
    s = sample(extract=3.0, dedupe=1.0, upload=0.5, append=0.5, reply=2.0)
    assert s.replied == pytest.approx(7.0)


def test_replied_is_never_less_than_stored():
    s = sample(extract=2.0, dedupe=1.0, reply=0.5)
    assert s.replied >= s.stored


def test_stored_ignores_stages_that_are_absent():
    """Tahap yang tidak terpicu tidak boleh membuat hasilnya negatif atau gagal."""
    s = sample(extract=2.0)
    assert s.stored == pytest.approx(2.0)


# ------------------------------------------- operand dan status

def test_verdict_uses_the_mean_of_stored_not_the_max():
    """Satu gambar yang sangat lambat tidak boleh menentukan status sendiri."""
    slowest = [sample(file=f"{i}.jpg", extract=4.0, dedupe=0.2) for i in range(9)]
    one = sample(file="x.jpg", extract=40.0, dedupe=0.2)
    c = sc03.compute(slowest + [one])
    # rata-rata = (9*4.2 + 40.2) / 10 = 7.8  -> di atas target
    assert c["mean_stored"] > 5.0
    assert c["stored"]["max"] == pytest.approx(40.2)


def test_target_is_five_seconds():
    assert sc03.TARGET_SECONDS == 5.0


def test_pass_when_mean_is_at_or_below_target():
    c = sc03.compute([sample(extract=4.0, dedupe=1.0)])
    assert c["mean_stored"] == pytest.approx(5.0)
    assert c["pass"] is True
    assert sc03.verdict(c) == "TERCAPAI"


def test_fail_when_mean_is_above_target():
    c = sc03.compute([sample(extract=5.0, dedupe=1.0)])
    assert c["pass"] is False
    assert sc03.verdict(c) == "BELUM TERCAPAI"


def test_no_samples_never_reports_pass():
    """Nol pengukuran bukan hasil; jangan pernah dianggap lulus."""
    c = sc03.compute([])
    assert c["pass"] is False
    assert c["measured"] == 0


def test_failed_samples_do_not_enter_the_average():
    """Gambar yang gagal diukur bukan waktu 0 detik."""
    ok = [sample(extract=4.0, dedupe=1.0)]
    failed = [sample(file="g.jpg", ok=False)]
    c = sc03.compute(ok + failed)
    assert c["measured"] == 1
    assert c["failed"] == 1
    assert c["mean_stored"] == pytest.approx(5.0)


# ------------------------------------------- laporan

def test_report_names_the_judged_number_before_the_status():
    """Sama seperti SC-01 dan SC-02: status tanpa operand adalah teka-teki."""
    c = sc03.compute([sample(extract=6.0, dedupe=1.0)])
    text = sc03.report(c)
    assert text.index("Angka yang dinilai") < text.index("Status")
    assert "tersimpan" in text


def test_report_states_the_target_in_seconds():
    c = sc03.compute([sample(extract=6.0, dedupe=1.0)])
    text = sc03.report(c)
    assert "5 detik" in text


def test_report_shows_the_stricter_definition_separately():
    """Definisi pengguna dilaporkan sebagai angka lain, bukan sebagai status."""
    c = sc03.compute([sample(extract=4.0, dedupe=1.0, reply=2.0)], reply_measured=True)
    text = sc03.report(c)
    assert "balasan Telegram" in text
    assert "tidak dipakai menilai target" in text


def test_report_does_not_print_zero_for_a_mocked_stage():
    """0,00 detik terbaca sebagai 'Telegram instan', padahal tidak dijalankan."""
    c = sc03.compute([sample(extract=4.0, dedupe=1.0)], reply_measured=False)
    text = sc03.report(c)
    assert "tidak diukur" in text
    # baris tahap reply tidak boleh menampilkan 0.00 detik
    for row in text.splitlines():
        if "reply" in row:
            assert "0.00 detik" not in row


def test_report_counts_samples_over_target():
    c = sc03.compute([sample(file="a.jpg", extract=2.0),
                      sample(file="b.jpg", extract=9.0)])
    text = sc03.report(c)
    assert "1 dari 2" in text


def test_report_lists_stage_breakdown():
    """Tanpa pecahan tahap, tidak ada cara tahu waktu habis di mana."""
    c = sc03.compute([sample(extract=4.0, dedupe=1.0, append=0.2)])
    text = sc03.report(c)
    for stage in ("extract", "dedupe", "append"):
        assert stage in text


def test_write_report_creates_both_files(tmp_path):
    c = sc03.compute([sample(extract=4.0, dedupe=1.0)])
    sc03.write_report(c, tmp_path)
    assert (tmp_path / "sc03_report.txt").exists()
    assert (tmp_path / "sc03_metrics.json").exists()
