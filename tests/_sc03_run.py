"""Ukur SC-03 pada seluruh gambar, apa adanya, dengan kemampuan melanjutkan.

Hasil disimpan per baris ke `sc03_samples.csv` supaya run yang terputus bisa
dilanjutkan tanpa memanggil model ulang untuk gambar yang sudah selesai.

Dijalankan:  python3 tests/_sc03_run.py [--limit N] [--restart]
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import _sc03_probe as probe  # noqa: E402

probe.prepare_env()

import main  # noqa: E402
import httpx  # noqa: E402
import sc03_latency as sc03  # noqa: E402

probe.prepare_client(main)

OUT = REPO / "sc-out"
OUT.mkdir(exist_ok=True)
SAMPLES = OUT / "sc03_samples.csv"
COLUMNS = ["file", "ok", "error", "status", "row"] + list(sc03.STAGES) + ["stored", "replied"]


def read_samples() -> dict[str, dict]:
    if not SAMPLES.exists():
        return {}
    with SAMPLES.open(encoding="utf-8") as f:
        return {r["file"]: r for r in csv.DictReader(f)}


def write_row(row: dict) -> None:
    is_new = not SAMPLES.exists()
    with SAMPLES.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if is_new:
            w.writeheader()
        w.writerow(row)


async def run_all(limit: int | None, restart: bool) -> None:
    if restart and SAMPLES.exists():
        SAMPLES.unlink()

    existing = read_samples()

    image_dir = REPO / "dataset/Bukti Transaksi Januari 2026"
    everything = sorted(image_dir.glob("*.jpg"))
    if not everything:
        print("TIDAK ADA GAMBAR — jalankan --download dulu")
        return

    # Hanya yang punya acuan (65 pasangan), bukan 118 foto.
    pairs = REPO / "dataset/pairs.csv"
    with pairs.open(encoding="utf-8") as f:
        reference_names = [r["file"] for r in csv.DictReader(f)]
    aimed = [p for p in everything if p.name in set(reference_names)]
    if limit:
        aimed = aimed[:limit]

    remaining = [p for p in aimed if p.name not in existing]
    print(f"total sasaran     : {len(aimed)}")
    print(f"sudah ada         : {len(aimed) - len(remaining)}")
    print(f"akan diukur       : {len(remaining)}")
    print()

    # Telegram di-mock: tidak ada bot token, dan tidak boleh kirim ke orang.
    async def fake_tg(client, method, **kw):
        return {"ok": True}

    main.tg_call = fake_tg

    async with httpx.AsyncClient(timeout=180) as client:
        for i, path in enumerate(remaining, 1):
            t0 = time.perf_counter()
            sample = await probe.measure_one(main, client, path.name, path.read_bytes())
            row = {
                "file": sample.file,
                "ok": sample.ok,
                "error": sample.error,
                "status": getattr(sample, "status", ""),
                "row": getattr(sample, "row", 0),
                **{s: round(sample.stages.get(s, 0.0), 4) for s in sc03.STAGES},
                "stored": round(sample.stored, 4),
                "replied": round(sample.replied, 4),
            }
            write_row(row)
            status = "ok" if sample.ok else f"GAGAL {sample.error[:40]}"
            print(f"  [{i:3}/{len(remaining)}] {path.name:42} "
                  f"stored={sample.stored:6.2f}s  {status}", flush=True)

    # Ringkasan
    data = read_samples()
    samples = []
    for r in data.values():
        s = sc03.Sample(file=r["file"], ok=(r["ok"] == "True"),
                        error=r.get("error", ""))
        for st in sc03.STAGES:
            try:
                s.stages[st] = float(r.get(st) or 0)
            except ValueError:
                s.stages[st] = 0.0
        samples.append(s)

    # Telegram di-mock di harness ini, jadi tahap reply tidak diukur sungguhan.
    c = sc03.compute(samples, reply_measured=False)
    sc03.write_report(c, OUT, "Sumber data: diukur langsung pada rantai produksi "
                              "dengan folder penyimpanan sandbox.")
    print()
    print(sc03.report(c))


if __name__ == "__main__":
    limit = None
    restart = "--restart" in sys.argv
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    asyncio.run(run_all(limit, restart))
