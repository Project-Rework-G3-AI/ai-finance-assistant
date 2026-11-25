"""Pengukur SC-05: jalankan jalur Telegram asli dengan Telegram dan Sheets tiruan.

Tidak butuh kunci AI, tidak butuh Google, tidak butuh jaringan. Waktu jalan di
bawah satu detik.

    python3 tests/_sc05_run.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import sc05_dedupe as sc05  # noqa: E402

OUT = REPO / "sc-out"

# Jumlah gambar uji. Gambarnya dibuat di dalam test, bukan diambil dari dataset,
# supaya isinya terkendali dan tidak menyentuh data perusahaan.
IMAGE_COUNT = 5


def main() -> int:
    import main as app

    cases = asyncio.run(sc05.measure(app, IMAGE_COUNT))
    result = sc05.compute(cases)
    sc05.write_report(
        result, OUT,
        "Sumber data: `handle_update` dan `write_cash_report` dari main.py "
        "dipanggil apa adanya; Telegram, Google Sheets, dan ekstraksi AI diganti "
        "tiruan. Yang dinilai adalah logika dedup yang sebenarnya.")
    print(sc05.report(result))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
