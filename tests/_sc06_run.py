"""Harness SC-06: ukur kelengkapan field ekstraksi pada seluruh gambar dataset.

Memanggil penyedia model dengan payload yang **sama persis** seperti produksi,
lalu menyimpan balasan mentahnya. Penyimpanan mentah itu penting: penilaian
kelengkapan dilakukan pada balasan model, bukan pada hasil `main.extract()` yang
sudah menutupi field kosong dengan nilai bawaan.

Biaya: satu panggilan model per gambar. Tanpa `--limit`, 65 gambar diproses.

Dijalankan:

    python3 tests/_sc06_run.py                # semua gambar di pairs.csv
    python3 tests/_sc06_run.py --limit 5      # uji cepat
    python3 tests/_sc06_run.py --restart      # hitung ulang dari nol
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

import sc_common as common  # noqa: E402
import sc06_extraction as sc06  # noqa: E402

OUT = REPO / "sc-out"
SAMPLES = OUT / "sc06_samples.csv"
# Yang disimpan adalah fakta: balasan mentah model apa adanya. Penilaian
# diturunkan ulang dari situ, sehingga mengubah aturan penilaian tidak
# memaksa memanggil model lagi (dan tidak menambah biaya).
COLUMNS = ["file", "ok", "error", "seconds", "raw"]


def read_env() -> None:
    """Baca `.env` di akar repo, sama seperti aplikasi."""
    path = REPO / ".env"
    if not path.exists():
        return
    for row in path.read_text(encoding="utf-8").splitlines():
        row = row.strip()
        if not row or row.startswith("#") or "=" not in row:
            continue
        key, _, value = row.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def credentials() -> tuple[str, str, str]:
    """Kunci, base URL, dan model. Gagal jelas bila salah satu kosong."""
    key = (os.getenv("AI_API_KEY") or "").strip()
    base = (os.getenv("AI_BASE_URL") or "").strip().rstrip("/")
    model = (os.getenv("AI_MODEL") or "").strip()
    kurang = [n for n, v in (("AI_API_KEY", key), ("AI_BASE_URL", base),
                             ("AI_MODEL", model)) if not v]
    if kurang:
        raise SystemExit(
            f"{', '.join(kurang)} kosong. Isi .env lebih dulu (lihat .env.example).")
    return key, base, model


def production_prompt() -> str:
    """Prompt yang sama persis dengan `main._vision_extract`."""
    import main

    teks = Path(main.__file__).read_text(encoding="utf-8")
    awal = teks.index("prompt = (")
    akhir = teks.index("if caption:", awal)
    ruang: dict = {}
    exec(teks[awal:akhir], {"KAT": main.KAT}, ruang)  # noqa: S102
    return ruang["prompt"]


async def call_model(client, key: str, base: str, model: str, prompt: str,
                     name: str, image: bytes, caption: str = "") -> dict:
    """Satu panggilan model. Kembalikan dict berisi balasan mentah."""
    b64 = base64.b64encode(image).decode()
    mime = "image/png" if name.lower().endswith(".png") else "image/jpeg"
    teks_prompt = prompt + (f"\nCaption Telegram: {caption}" if caption else "")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": teks_prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ]}],
        "temperature": 0,
    }
    mulai = time.time()
    r = await client.post(f"{base}/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
                          json=payload, timeout=180)
    detik = time.time() - mulai
    r.raise_for_status()
    isi = r.json()["choices"][0]["message"]["content"]

    import re

    m = re.search(r"\{.*\}", isi or "", re.S)
    if not m:
        raise ValueError(f"balasan model bukan JSON: {(isi or '')[:120]}")
    return {"raw": json.loads(m.group(0)), "seconds": round(detik, 2)}


async def measure(rows: list[dict], limit: int | None, restart: bool) -> list[dict]:
    """Ukur semua baris, simpan bertahap supaya aman bila proses mati."""
    import httpx

    key, base, model = credentials()
    prompt = production_prompt()
    folder = common.images_dir()

    if restart and SAMPLES.exists():
        SAMPLES.unlink()
    OUT.mkdir(parents=True, exist_ok=True)

    sudah: dict[str, dict] = {}
    if SAMPLES.exists():
        with open(SAMPLES, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                sudah[row["file"]] = row
        if sudah:
            print(f"memakai {len(sudah)} hasil lama; pakai --restart untuk menghitung ulang")

    dipilih = rows[:limit] if limit else rows
    hasil: list[dict] = []

    baru = not SAMPLES.exists()
    with open(SAMPLES, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if baru:
            w.writeheader()

        async with httpx.AsyncClient() as client:
            for i, row in enumerate(dipilih, 1):
                name = str(row.get("file") or "").strip()
                if name in sudah and sudah[name].get("ok") == "ya":
                    hasil.append({"file": name,
                                  "raw": json.loads(sudah[name]["raw"] or "{}"),
                                  "error": ""})
                    continue

                path = folder / name
                try:
                    keluaran = await call_model(client, key, base, model, prompt,
                                                name, path.read_bytes(),
                                                str(row.get("caption") or ""))
                    catat = {"file": name, "ok": "ya", "error": "",
                             "seconds": keluaran["seconds"],
                             "raw": json.dumps(keluaran["raw"], ensure_ascii=False)}
                    hasil.append({"file": name, "raw": keluaran["raw"], "error": ""})
                except Exception as e:
                    pesan = f"{type(e).__name__}: {e}"[:300]
                    catat = {"file": name, "ok": "tidak", "error": pesan,
                             "seconds": "", "raw": ""}
                    hasil.append({"file": name, "raw": {}, "error": pesan})
                w.writerow(catat)
                f.flush()
                print(f"  {i}/{len(dipilih)} {name} "
                      f"{'ok' if catat['ok'] == 'ya' else 'GAGAL'}")
    return hasil


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ukur SC-06: kelengkapan field ekstraksi")
    p.add_argument("--limit", type=int, default=None,
                   help="batasi jumlah gambar (untuk uji cepat)")
    p.add_argument("--restart", action="store_true",
                   help="hapus hasil lama lalu hitung ulang")
    args = p.parse_args(argv)

    read_env()
    common.load_env()
    rows = common.read_pairs(common.pairs_file())
    hasil = asyncio.run(measure(rows, args.limit, args.restart))

    laporan = sc06.compute(hasil)
    txt, csv_path = sc06.write_report(laporan, OUT)
    print()
    print(txt.read_text(encoding="utf-8"))
    print(f"rincian per gambar: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
