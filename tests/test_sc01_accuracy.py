"""SC-01: akurasi usulan kategori terhadap kategori yang ditetapkan Admin.

Yang diuji di sini ada dua lapis, dan pembedaannya penting:

1. Perhitungan metrik — selalu jalan, tidak butuh AI maupun jaringan. Bagian ini
   yang menjaga agar angka di laporan tidak salah rumus.
2. Eksekusi model pada dataset asli — hanya jalan bila AI_API_KEY, daftar
   pasangan, dan gambarnya tersedia. Tanpa itu di-skip, bukan gagal.

Batas ruang lingkup yang diuji: hanya `main.extract` (gambar -> kategori).
Penulisan ke Google Sheets dan Drive tidak dipanggil sama sekali, sehingga
spreadsheet perusahaan tidak tersentuh dan hasil bisa diulang.

Jalankan:

    # hanya uji rumus metrik
    pytest tests/test_sc01_accuracy.py -v

    # sekaligus menjalankan model pada 65 pasangan (berbiaya ~Rp1.100)
    SC01_SET_UJI=/path/set_uji_1to1.csv \\
    SC01_IMG_DIR=/path/gambar \\
    AI_API_KEY=... pytest tests/test_sc01_accuracy.py -v
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import pytest

AKAR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AKAR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sc01_metrics import hitung  # noqa: E402

SET_UJI = os.environ.get("SC01_SET_UJI", "").strip()
IMG_DIR = os.environ.get("SC01_IMG_DIR", "").strip()

TARGET_SC01 = 0.85


# ---------------------------------------------------------------- metrik murni

def test_akurasi_dihitung_dari_kecocokan():
    pasangan = [
        {"kategori_acuan": "A", "kategori_usulan": "A"},
        {"kategori_acuan": "A", "kategori_usulan": "B"},
        {"kategori_acuan": "B", "kategori_usulan": "B"},
        {"kategori_acuan": "B", "kategori_usulan": "B"},
    ]
    h = hitung(pasangan)
    assert h.total == 4
    assert h.benar == 3
    assert h.akurasi == pytest.approx(0.75)


def test_baseline_adalah_kelas_terbanyak():
    """Baseline harus mengikuti sebaran data, bukan angka tetap."""
    pasangan = (
        [{"kategori_acuan": "Transfer Antar Bank", "kategori_usulan": "x"}] * 49
        + [{"kategori_acuan": "Pendapatan", "kategori_usulan": "x"}] * 12
        + [{"kategori_acuan": "Biaya-Gaji", "kategori_usulan": "x"}] * 4
    )
    h = hitung(pasangan)
    assert h.total == 65
    assert h.baseline_label == "Transfer Antar Bank"
    assert h.baseline == pytest.approx(49 / 65)
    # Model yang salah semua tetap punya akurasi 0, bukan baseline.
    assert h.akurasi == 0.0
    assert h.lift == pytest.approx(-49 / 65)


def test_lift_negatif_saat_model_kalah_dari_tebakan_konstan():
    """Akurasi tinggi tidak berarti apa-apa bila di bawah baseline."""
    pasangan = (
        [{"kategori_acuan": "Mayoritas", "kategori_usulan": "Lain"}] * 9
        + [{"kategori_acuan": "Minoritas", "kategori_usulan": "Minoritas"}] * 1
    )
    h = hitung(pasangan)
    assert h.akurasi == pytest.approx(0.1)
    assert h.baseline == pytest.approx(0.9)
    assert h.lift < 0


def test_macro_average_tidak_tertutup_kelas_mayoritas():
    """Kelas jarang harus berbobot sama di macro-average."""
    # Akurasi micro 90% (9 dari 10 benar) tetapi kelas B selalu salah.
    pasangan = (
        [{"kategori_acuan": "A", "kategori_usulan": "A"}] * 9
        + [{"kategori_acuan": "B", "kategori_usulan": "A"}] * 1
    )
    h = hitung(pasangan)
    assert h.akurasi == pytest.approx(0.9)
    assert h.per_kategori["A"]["recall"] == pytest.approx(1.0)
    assert h.per_kategori["B"]["recall"] == pytest.approx(0.0)
    # (1.0 + 0.0) / 2, bukan 0.9
    assert h.macro_avg == pytest.approx(0.5)
    assert h.macro_avg < h.akurasi


def test_kategori_kosong_dihitung_salah_bukan_dilewati():
    """Model yang tidak menjawab tetap masuk penyebut, tidak boleh disembunyikan."""
    pasangan = [
        {"kategori_acuan": "A", "kategori_usulan": "A"},
        {"kategori_acuan": "B", "kategori_usulan": ""},
    ]
    h = hitung(pasangan)
    assert h.total == 2
    assert h.benar == 1
    assert h.per_kategori["B"]["recall"] == 0.0


def test_confusion_matrix_menjumlah_sesuai_total():
    pasangan = [
        {"kategori_acuan": "A", "kategori_usulan": "A"},
        {"kategori_acuan": "A", "kategori_usulan": "B"},
        {"kategori_acuan": "B", "kategori_usulan": "B"},
    ]
    h = hitung(pasangan)
    total_sel = sum(sum(d.values()) for d in h.confusion.values())
    assert total_sel == h.total
    assert h.confusion["A"]["A"] == 1
    assert h.confusion["A"]["B"] == 1


def test_daftar_kosong_ditolak():
    with pytest.raises(ValueError):
        hitung([])


# ------------------------------------------------- batas ruang lingkup SC-01

def test_runner_tidak_menulis_ke_sheets_atau_drive():
    """SC-01 hanya mengukur akurasi, jadi jalur tulis Google tidak boleh dipanggil.

    Bila suatu saat runner ikut memanggil write_cash_report, test ini gagal dan
    mencegah spreadsheet perusahaan tercemar saat evaluasi.
    """
    sys.path.insert(0, str(AKAR))
    import main  # noqa: E402

    dipanggil: list[str] = []
    for nama in ("write_cash_report", "upload_drive", "push_pending", "flush_pending"):
        if hasattr(main, nama):
            def _jebakan(*a, _n=nama, **kw):
                dipanggil.append(_n)
                raise AssertionError(f"{_n} dipanggil saat evaluasi SC-01")
            setattr(main, nama, _jebakan)

    import sc01_harness  # noqa: E402

    # Runner hanya boleh menyentuh main.extract; modulnya tidak boleh mengimpor
    # jalur tulis sebagai fungsi yang dipanggil saat impor.
    assert not dipanggil, f"fungsi tulis terpanggil: {dipanggil}"
    assert hasattr(sc01_harness, "jalankan")


# ------------------------------------------------------- eksekusi model asli

butuh_dataset = pytest.mark.skipif(
    not SET_UJI or not Path(SET_UJI).is_file() or not IMG_DIR or not Path(IMG_DIR).is_dir(),
    reason="SC01_SET_UJI / SC01_IMG_DIR tidak tersedia; dataset perusahaan privat",
)
butuh_ai = pytest.mark.skipif(
    not os.environ.get("AI_API_KEY", "").strip(),
    reason="AI_API_KEY kosong; SC-01 mengukur model asli, bukan mock",
)


@butuh_dataset
def test_set_uji_lengkap_dan_berlabel():
    """Set uji harus 1:1 — tiap baris punya gambar dan kategori acuan."""
    with open(SET_UJI, encoding="utf-8-sig", newline="") as f:
        baris = [r for r in csv.DictReader(f) if (r.get("file") or "").strip()]

    assert baris, "set uji kosong"
    for r in baris:
        assert (r.get("kategori_acuan") or "").strip(), f"kategori acuan kosong: {r.get('file')}"
        assert (Path(IMG_DIR) / r["file"].strip()).is_file(), f"gambar tidak ada: {r['file']}"

    # Setiap gambar hanya boleh muncul sekali agar tidak ada baris dihitung ganda.
    nama = [r["file"].strip() for r in baris]
    assert len(nama) == len(set(nama)), "ada gambar yang dipakai lebih dari satu baris"


@butuh_dataset
@butuh_ai
def test_sc01_akurasi_memenuhi_target(tmp_path):
    """Jalankan model asli pada seluruh set uji dan bandingkan dengan target BRD.

    Hasil ditulis ke tmp_path agar tidak mengotori repo. Test ini sengaja tidak
    dijalankan pada CI biasa karena memanggil API berbayar.
    """
    import asyncio

    import httpx

    import main  # noqa: E402
    from sc01_harness import baca_pasangan  # noqa: E402

    pasangan = baca_pasangan(SET_UJI)
    hasil: list[dict] = []

    async def jalan():
        async with httpx.AsyncClient(timeout=120.0) as client:
            for p in pasangan:
                jalur = Path(IMG_DIR) / p["file"].strip()
                rec = await main.extract(client, jalur.name, jalur.read_bytes(), "")
                hasil.append({
                    "file": p["file"].strip(),
                    "kategori_acuan": p["kategori_acuan"].strip(),
                    "kategori_usulan": str(rec.get("kategori") or "").strip(),
                })

    asyncio.run(jalan())

    h = hitung(hasil)

    # Simpan bukti sebelum menyatakan apa pun, supaya hasil run tidak hilang
    # bila assertion di bawah gagal.
    with open(tmp_path / "hasil_per_baris.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["file", "kategori_acuan", "kategori_usulan"])
        w.writeheader()
        w.writerows(hasil)
    (tmp_path / "ringkasan.txt").write_text(h.ringkas(), encoding="utf-8")

    print("\n" + h.ringkas())
    assert h.total == len(pasangan)
    assert h.akurasi >= TARGET_SC01, (
        f"akurasi {h.akurasi:.1%} di bawah target {TARGET_SC01:.0%}. "
        f"Baseline kelas mayoritas {h.baseline:.1%} ({h.baseline_label}); "
        f"lift {h.lift:+.1%}. Rincian: {tmp_path/'hasil_per_baris.csv'}"
    )
