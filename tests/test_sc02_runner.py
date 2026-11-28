"""SC-02 di dalam runner: tidak menuntut dataset yang tidak dibacanya.

SC-02 mengukur kelengkapan dari `results_per_row.csv` saja. Nilai acuan dari
`pairs.csv` sudah tidak dipakai. Karena itu `--sc02` tidak boleh gagal hanya
karena dataset gambar atau `pairs.csv` belum diunduh, dan pesan galatnya tidak
boleh menyuruh mengunduh dataset.

Cacat yang dikunci di sini pernah terjadi: setelah jalur akurasi dibuang,
`--sc02` masih menuntut `pairs.csv` lewat pemeriksaan kesiapan umum, sehingga
perintah yang seharusnya gratis berhenti dengan pesan yang menyesatkan.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc_runner  # noqa: E402

HASIL_CONTOH = (
    "file,reference_category,proposed_category,match,reference_amount,"
    "proposed_amount,amount_diff,reference_date,proposed_date,proposed_bank,"
    "proposed_direction,proposed_note,mode,note,model_note,seconds\r\n"
    "a.jpg,Bahan Baku,Bahan Baku,ya,1000,1000,0,2026-01-01,"
    "2026-01-01 08:00:00,BNI,keluar,keterangan,vision,"
    "Ekstraksi AI — wajib ditinjau sebelum dipakai.,keterangan,8.0\r\n"
)


def test_sc02_is_known_not_to_need_the_dataset():
    assert "sc02" in sc_runner.NEEDS_NO_DATASET


def test_sc02_runs_without_pairs_csv(tmp_path):
    """`--sc02` harus jalan hanya dengan hasil ekstraksi, tanpa `pairs.csv`."""
    (tmp_path / "results_per_row.csv").write_text(HASIL_CONTOH, encoding="utf-8")

    hasil = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "sc_runner.py"),
         "--sc02", "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120,
    )
    gabung = hasil.stdout + hasil.stderr
    assert "daftar pasangan belum ada" not in gabung, (
        "SC-02 masih menuntut pairs.csv yang tidak dibacanya")
    assert "SC-02" in gabung


def test_sc02_without_results_gives_a_useful_message(tmp_path):
    """Tanpa hasil ekstraksi, pesannya harus menyebut apa yang harus dilakukan."""
    hasil = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "sc_runner.py"),
         "--sc02", "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=str(ROOT), timeout=120,
    )
    gabung = hasil.stdout + hasil.stderr
    assert "results_per_row.csv" in gabung
    assert "daftar pasangan" not in gabung


def test_sc02_still_asks_for_the_model_key_when_measuring():
    """Menilai ulang gratis, tetapi mengukur dari nol tetap butuh kunci model.

    `--sc02` sendiri hanya merangkum, jadi ia tidak boleh ikut jalur yang
    menuntut `AI_API_KEY`. Yang dijaga di sini: SC-02 tidak masuk FREE_CRITERIA,
    karena tanpa hasil ekstraksi ia memang harus mengukur dulu.
    """
    assert "sc02" not in sc_runner.FREE_CRITERIA
