"""Harness SC-06: jalankan pengukuran tanpa kredensial dan tanpa jaringan.

Membandingkan kolom wajib template perusahaan dengan kolom keluaran aplikasi.
Gratis: tidak memanggil model, tidak menulis ke Google Sheets.

Contoh:
    python3 tests/_sc06_run.py
    python3 tests/_sc06_run.py --download        # unduh template dulu
    python3 tests/_sc06_run.py --template-dir /path/ke/template
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc06_columns as sc06

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ukur SC-06: kolom wajib cash report terpetakan semua")
    parser.add_argument(
        "--download", action="store_true",
        help="unduh template perusahaan dari repo dataset lebih dulu")
    parser.add_argument(
        "--template-dir", default=str(ROOT / sc06.TEMPLATE_DIR),
        help="folder berisi berkas template perusahaan")
    parser.add_argument(
        "--out", default=str(ROOT / "sc-out"),
        help="folder keluaran laporan")
    args = parser.parse_args()

    directory = Path(args.template_dir)

    if args.download:
        print(f"Mengunduh template ke {directory} ...")
        berkas = sc06.download_templates(directory)
        for b in berkas:
            print(f"  {b.name} ({b.stat().st_size} byte)")

    try:
        report = sc06.compute(directory)
    except FileNotFoundError as e:
        print(f"\nGAGAL: {e}")
        return 1

    txt, csv_path = sc06.write_report(report, Path(args.out))
    print()
    print(txt.read_text(encoding="utf-8"))
    print(f"Laporan : {txt}")
    print(f"Rincian : {csv_path}")

    return 0 if report.pass_verdict else 1


if __name__ == "__main__":
    sys.exit(main())
