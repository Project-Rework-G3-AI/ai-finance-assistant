"""SC-01: akurasi usulan kategori terhadap kategori yang ditetapkan Admin.

Yang diuji ada dua lapis, dan pembedaannya penting:

1. Perhitungan metrik — selalu jalan, tanpa AI maupun jaringan. Bagian ini yang
   menjaga agar angka di laporan tidak salah rumus.
2. Eksekusi model pada dataset asli — hanya jalan bila konfigurasi di `.env`
   lengkap. Tanpa itu di-skip dengan alasan yang menyebut apa yang kurang.

Batas ruang lingkup: hanya `main.extract` (gambar -> kategori). Penulisan ke
Google Sheets dan Drive tidak dipanggil sama sekali, sehingga spreadsheet
perusahaan tidak tersentuh dan hasil bisa diulang.

Persiapan sekali saja (lihat docs/sc01-cara-menjalankan.md):

    cp .env.example .env
    # isi AI_API_KEY
    python3 tests/sc01_harness.py --download     # unduh 65 gambar

Menjalankan:

    pytest tests/test_sc01_accuracy.py -v                    # rumus metrik saja
    pytest tests/test_sc01_accuracy.py -v -m sc01_model      # + panggil model
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc01_config as cfg  # noqa: E402
from sc01_metrics import compute  # noqa: E402

cfg.load_env()

TARGET_SC01 = 0.85


# ---------------------------------------------------------------- metrik murni

def test_accuracy_computed_from_matches():
    pairs = [
        {"reference_category": "A", "proposed_category": "A"},
        {"reference_category": "A", "proposed_category": "B"},
        {"reference_category": "B", "proposed_category": "B"},
        {"reference_category": "B", "proposed_category": "B"},
    ]
    m = compute(pairs)
    assert m.total == 4
    assert m.correct == 3
    assert m.accuracy == pytest.approx(0.75)


def test_baseline_is_the_majority_class():
    """Baseline harus mengikuti sebaran data, bukan angka tetap."""
    pairs = (
        [{"reference_category": "Transfer Antar Bank", "proposed_category": "x"}] * 49
        + [{"reference_category": "Pendapatan", "proposed_category": "x"}] * 12
        + [{"reference_category": "Biaya-Gaji", "proposed_category": "x"}] * 4
    )
    m = compute(pairs)
    assert m.total == 65
    assert m.majority_label == "Transfer Antar Bank"
    assert m.baseline == pytest.approx(49 / 65)
    # Model yang salah semua tetap punya akurasi 0, bukan baseline.
    assert m.accuracy == 0.0
    assert m.lift == pytest.approx(-49 / 65)


def test_lift_is_negative_when_the_model_loses_to_a_constant_guess():
    """Akurasi tinggi tidak berarti apa-apa bila di bawah baseline."""
    pairs = (
        [{"reference_category": "Mayoritas", "proposed_category": "Lain"}] * 9
        + [{"reference_category": "Minoritas", "proposed_category": "Minoritas"}] * 1
    )
    m = compute(pairs)
    assert m.accuracy == pytest.approx(0.1)
    assert m.baseline == pytest.approx(0.9)
    assert m.lift < 0


def test_macro_average_is_not_dominated_by_the_majority_class():
    """Kelas jarang harus berbobot sama di macro-average."""
    # Akurasi micro 90% (9 dari 10 benar) tetapi kelas B selalu salah.
    pairs = (
        [{"reference_category": "A", "proposed_category": "A"}] * 9
        + [{"reference_category": "B", "proposed_category": "A"}] * 1
    )
    m = compute(pairs)
    assert m.accuracy == pytest.approx(0.9)
    assert m.per_category["A"]["recall"] == pytest.approx(1.0)
    assert m.per_category["B"]["recall"] == pytest.approx(0.0)
    # (1.0 + 0.0) / 2, bukan 0.9
    assert m.macro_avg == pytest.approx(0.5)
    assert m.macro_avg < m.accuracy


def test_empty_category_counts_as_wrong_not_skipped():
    """Model yang tidak menjawab tetap masuk penyebut, tidak boleh disembunyikan."""
    pairs = [
        {"reference_category": "A", "proposed_category": "A"},
        {"reference_category": "B", "proposed_category": ""},
    ]
    m = compute(pairs)
    assert m.total == 2
    assert m.correct == 1
    assert m.per_category["B"]["recall"] == 0.0


def test_confusion_matrix_sums_to_the_total():
    pairs = [
        {"reference_category": "A", "proposed_category": "A"},
        {"reference_category": "A", "proposed_category": "B"},
        {"reference_category": "B", "proposed_category": "B"},
    ]
    m = compute(pairs)
    total_cells = sum(sum(d.values()) for d in m.confusion.values())
    assert total_cells == m.total
    assert m.confusion["A"]["A"] == 1
    assert m.confusion["A"]["B"] == 1


def test_empty_input_is_rejected():
    with pytest.raises(ValueError):
        compute([])


# ------------------------------------------------- batas ruang lingkup SC-01

def test_runner_does_not_write_to_sheets_or_drive():
    """SC-01 hanya mengukur akurasi, jadi jalur tulis Google tidak boleh dipanggil.

    Bila suatu saat runner ikut memanggil write_cash_report, test ini gagal dan
    mencegah spreadsheet perusahaan tercemar saat evaluasi.
    """
    import main  # noqa: E402

    called: list[str] = []
    for name in ("write_cash_report", "upload_drive", "push_pending", "flush_pending"):
        if hasattr(main, name):
            def _trap(*a, _n=name, **kw):
                called.append(_n)
                raise AssertionError(f"{_n} dipanggil saat evaluasi SC-01")
            setattr(main, name, _trap)

    import sc01_harness  # noqa: E402

    assert not called, f"fungsi tulis terpanggil: {called}"
    assert hasattr(sc01_harness, "run_pairs")


# ------------------------------------------------------- eksekusi model asli

_ready, _reason = cfg.ready(skip_ai_check=True)
needs_dataset = pytest.mark.skipif(not _ready, reason=_reason)
needs_ai = pytest.mark.skipif(
    not os.getenv("AI_API_KEY", "").strip(),
    reason="AI_API_KEY kosong; SC-01 mengukur model asli, bukan mock",
)
# Test yang memanggil API berbayar harus diminta secara eksplisit. Tanpa ini,
# `pytest` biasa akan menghabiskan puluhan panggilan dan belasan menit hanya
# karena .env kebetulan terisi.
opt_in = pytest.mark.skipif(
    not os.getenv("SC01_RUN_MODEL", "").strip(),
    reason="test model berbayar; set SC01_RUN_MODEL=1 untuk menjalankannya",
)


@needs_dataset
def test_evaluation_set_is_complete_and_labelled():
    """Set uji harus 1:1 — tiap baris punya gambar dan kategori acuan."""
    rows = cfg.read_pairs(cfg.pairs_file())
    folder = cfg.images_dir()

    assert rows, "set uji kosong"
    for r in rows:
        assert (r.get("reference_category") or "").strip(), \
            f"kategori acuan kosong: {r.get('file')}"
        assert (folder / r["file"].strip()).is_file(), f"gambar tidak ada: {r['file']}"

    # Setiap gambar hanya boleh muncul sekali agar tidak ada baris dihitung ganda.
    names = [r["file"].strip() for r in rows]
    assert len(names) == len(set(names)), "ada gambar yang dipakai lebih dari satu baris"


@needs_dataset
@needs_ai
@opt_in
@pytest.mark.sc01_model
def test_sc01_accuracy_meets_the_target(tmp_path):
    """Jalankan model asli pada seluruh set uji dan bandingkan dengan target BRD.

    Hasil ditulis ke tmp_path agar tidak mengotori repo. Test ini butuh opt-in
    ganda karena memanggil API berbayar dan berjalan belasan menit:

        SC01_RUN_MODEL=1 pytest -m sc01_model -v

    Untuk sekadar mengukur tanpa assertion, pakai runner:
        python3 tests/sc01_harness.py
    """
    import asyncio

    import httpx

    import main  # noqa: E402

    pairs = cfg.read_pairs(cfg.pairs_file())
    folder = cfg.images_dir()
    results: list[dict] = []

    async def _run():
        async with httpx.AsyncClient(timeout=120.0) as client:
            for p in pairs:
                image_path = folder / p["file"].strip()
                rec = cfg.normalize_extract(
                    await main.extract(client, image_path.name,
                                       image_path.read_bytes(), ""))
                results.append({
                    "file": p["file"].strip(),
                    "reference_category": p["reference_category"].strip(),
                    "proposed_category": str(rec.get("category") or "").strip(),
                })

    asyncio.run(_run())

    m = compute(results)

    # Simpan bukti sebelum menyatakan apa pun, supaya hasil run tidak hilang
    # bila assertion di bawah gagal.
    with open(tmp_path / "results_per_row.csv", "w",
              encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "reference_category",
                                          "proposed_category"])
        w.writeheader()
        w.writerows(results)
    (tmp_path / "summary.txt").write_text(m.summary(), encoding="utf-8")

    print("\n" + m.summary())
    assert m.total == len(pairs)
    assert m.accuracy >= TARGET_SC01, (
        f"akurasi {m.accuracy:.1%} di bawah target {TARGET_SC01:.0%}. "
        f"Baseline kelas mayoritas {m.baseline:.1%} ({m.majority_label}); "
        f"lift {m.lift:+.1%}. Rincian: {tmp_path/'results_per_row.csv'}"
    )
