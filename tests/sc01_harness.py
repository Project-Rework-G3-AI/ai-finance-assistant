"""Runner SC-01: jalankan model asli pada dataset berlabel, simpan hasil per baris.

Alur yang diuji sengaja dipersempit ke satu hal: gambar -> kategori. Karena itu
hanya `main.extract` yang dijalankan apa adanya, sedangkan penulisan ke Google
Sheets/Drive tidak dipanggil sama sekali. Dengan begitu spreadsheet perusahaan
tidak tersentuh dan hasil bisa diulang.

Hasil ditulis bertahap ke CSV setelah setiap gambar selesai diproses. Ini bukan
gaya berlebihan: run pertama di sesi sebelumnya sempat mati setelah puluhan
panggilan API berbayar, dan yang menyelamatkan hasilnya hanya karena CSV sudah
terlanjur ditulis.

Pemakaian:

    # 1. unduh gambar dataset (sekali saja)
    python3 tests/sc01_harness.py --download

    # 2. jalankan evaluasi (butuh AI_API_KEY)
    python3 tests/sc01_harness.py

    # 3. hitung ulang metrik dari CSV yang sudah ada (tanpa memanggil AI)
    python3 tests/sc01_harness.py --metrics-only

Lokasi dataset diatur di `.env` lewat SC01_PAIRS dan SC01_IMAGES.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc01_config as cfg  # noqa: E402

cfg.load_env()

import httpx  # noqa: E402

from sc01_metrics import compute  # noqa: E402

OUTPUT_COLUMNS = [
    "file", "reference_category", "proposed_category", "match",
    "reference_amount", "proposed_amount", "amount_diff",
    "reference_date", "proposed_date",
    "mode", "note", "model_note", "seconds",
]


def read_results(path: Path) -> dict[str, dict]:
    """Hasil yang sudah ada, dipakai untuk melanjutkan run yang terputus."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {(r.get("file") or "").strip(): r for r in csv.DictReader(f)}


async def run_pairs(pairs: list[dict], images_dir: Path, out: Path,
                    restart: bool = False) -> list[dict]:
    import main  # diimpor di dalam agar `--download` tidak butuh AI_API_KEY

    done = {} if restart else read_results(out)
    results = list(done.values())

    remaining = [p for p in pairs if (p.get("file") or "").strip() not in done]
    if done:
        print(f"melanjutkan: {len(done)} sudah ada, {len(remaining)} tersisa")
    if not remaining:
        return results

    if not main.AI_KEY:
        raise SystemExit(
            "AI_API_KEY kosong. SC-01 mengukur akurasi model, jadi tidak bisa "
            "dijalankan dalam mode mock."
        )
    print(f"model: {main.AI_MODEL} via {main.AI_BASE}")
    print(f"gambar: {images_dir}\nkeluaran: {out}\n")

    # Tulis header lebih dulu agar file tetap valid walau proses mati di tengah.
    write_header = not out.exists()
    f = open(out, "a", encoding="utf-8", newline="")
    w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
    if write_header:
        w.writeheader()
        f.flush()

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i, p in enumerate(remaining, 1):
            name = (p.get("file") or "").strip()
            image_path = images_dir / name
            if not image_path.exists():
                print(f"[{i}/{len(remaining)}] LEWATI {name}: file tidak ada")
                continue

            image_bytes = image_path.read_bytes()
            started = time.monotonic()
            try:
                rec = cfg.normalize_extract(
                    await main.extract(client, name, image_bytes, ""))
                error = ""
            except Exception as e:
                rec = {"category": "", "amount": None, "date": "",
                       "mode": "error", "note": "", "remark": ""}
                error = f"{type(e).__name__}: {e}"
            elapsed = time.monotonic() - started

            proposed = str(rec.get("category") or "").strip()
            reference = (p.get("reference_category") or "").strip()
            row = {
                "file": name,
                "reference_category": reference,
                "proposed_category": proposed,
                "match": "ya" if proposed == reference else "tidak",
                "reference_amount": (p.get("reference_amount") or "").strip(),
                "proposed_amount": rec.get("amount"),
                "amount_diff": _amount_diff(p.get("reference_amount"), rec.get("amount")),
                "reference_date": (p.get("reference_date") or "").strip(),
                "proposed_date": rec.get("date") or "",
                "mode": rec.get("mode") or ("error" if error else ""),
                "note": (rec.get("remark") or error)[:300],
                "model_note": (rec.get("note") or "")[:200],
                "seconds": round(elapsed, 2),
            }
            w.writerow(row)
            f.flush()
            os.fsync(f.fileno())
            results.append(row)

            mark = "OK " if row["match"] == "ya" else "SALAH"
            print(f"[{i}/{len(remaining)}] {mark} {name[:38]:40} "
                  f"{proposed[:34]:36} ({elapsed:.1f}s)")

    f.close()
    return results


def _amount_diff(reference, proposed) -> str:
    try:
        return str(int(float(reference)) - int(float(proposed)))
    except (TypeError, ValueError):
        return ""


def write_report(results: list[dict], out: Path) -> dict:
    """Hitung metrik lalu tulis laporan teks + metrics.json ke disk."""
    pairs = [{"reference_category": r["reference_category"],
              "proposed_category": r["proposed_category"],
              "file": r["file"]} for r in results if r.get("reference_category")]
    m = compute(pairs)

    lines = [
        "SC-01 — Akurasi usulan kategori",
        "=" * 60,
        m.summary(),
        "",
        "Target BRD: minimal 85%",
        f"Status    : {'TERCAPAI' if m.accuracy >= 0.85 else 'BELUM TERCAPAI'}",
        "",
        "Per kategori (diurutkan dari yang paling sering muncul)",
        "-" * 60,
        f"{'kategori':46} {'acuan':>5} {'benar':>5} {'recall':>7}",
    ]
    for label, d in sorted(m.per_category.items(), key=lambda kv: -kv[1]["reference"]):
        lines.append(f"{label[:46]:46} {d['reference']:5} {d['correct']:5} "
                     f"{d['recall']:6.0%}")

    lines += ["", "Confusion matrix (baris = acuan, kolom = usulan)", "-" * 60]
    for a in m.confusion:
        row = ", ".join(f"{u}={n}" for u, n in
                        sorted(m.confusion[a].items(), key=lambda kv: -kv[1]))
        lines.append(f"{a[:44]:46} -> {row}")

    if m.wrong:
        lines += ["", f"Baris yang salah ({len(m.wrong)})", "-" * 60]
        for s in m.wrong:
            lines.append(f"{s['file'][:44]:46} {s['reference'][:26]:28} -> {s['proposed'][:28]}")

    text = "\n".join(lines)
    (out / "report.txt").write_text(text, encoding="utf-8")
    (out / "metrics.json").write_text(
        json.dumps({
            "total": m.total, "correct": m.correct, "accuracy": m.accuracy,
            "baseline": m.baseline, "majority_label": m.majority_label,
            "lift": m.lift, "macro_avg": m.macro_avg,
            "per_category": m.per_category, "confusion": m.confusion,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"metrics": m, "text": text}


def main_cli() -> int:
    ap = argparse.ArgumentParser(
        description="Runner evaluasi SC-01 (akurasi kategori)")
    ap.add_argument("--download", action="store_true",
                    help="unduh gambar dataset dari repo, lalu berhenti")
    ap.add_argument("--pairs", default="", help="timpa SC01_PAIRS")
    ap.add_argument("--images", default="", help="timpa SC01_IMAGES")
    ap.add_argument("--out", default="sc01-out", help="folder keluaran (default: sc01-out)")
    ap.add_argument("--restart", action="store_true", help="abaikan hasil lama, proses dari awal")
    ap.add_argument("--repeat", type=int, default=1, metavar="N",
                    help="jalankan N kali lalu laporkan rentang akurasi (untuk mengukur kestabilan)")
    ap.add_argument("--metrics-only", action="store_true", help="hitung metrik tanpa memanggil AI")
    a = ap.parse_args()

    # Argumen CLI menang atas .env, supaya bisa dipakai tanpa menyunting file.
    if a.pairs:
        os.environ["SC01_PAIRS"] = a.pairs
    if a.images:
        os.environ["SC01_IMAGES"] = a.images

    if a.download:
        # Daftar pasangan diunduh dulu: tanpa itu tidak diketahui gambar mana
        # yang harus diambil. Keduanya ada di repo yang sama.
        cfg.download_pairs()
        folder = cfg.images_dir()
        print(f"mengunduh gambar ke: {folder}")
        downloaded, skipped = cfg.download_images(folder)
        print(f"selesai: {downloaded} diunduh, {skipped} sudah ada")
        is_ready, reason = cfg.ready(skip_ai_check=True)
        print(f"status: {'siap' if is_ready else 'BELUM siap'} — {reason}")
        return 0 if is_ready else 1

    out = Path(a.out)
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)

    if a.metrics_only:
        results = list(read_results(out / "results_per_row.csv").values())
        if not results:
            raise SystemExit(f"tidak ada hasil di {out / 'results_per_row.csv'}")
        r = write_report(results, out)
        print(r["text"])
        return 0

    is_ready, reason = cfg.ready()
    if not is_ready:
        raise SystemExit(f"belum siap: {reason}")

    pairs = cfg.read_pairs(cfg.pairs_file())
    print(f"pasangan: {len(pairs)}")

    if a.repeat > 1:
        # Dijalankan berulang untuk melihat sebaran angka. Model tidak menjamin
        # hasil identik antar-run, jadi satu angka saja bisa menyesatkan.
        all_metrics = []
        for n in range(1, a.repeat + 1):
            print(f"\n===== run {n} dari {a.repeat} =====")
            run_dir = out / f"run-{n}"
            run_dir.mkdir(parents=True, exist_ok=True)
            run_results = asyncio.run(run_pairs(pairs, cfg.images_dir(),
                                                run_dir / "results_per_row.csv", True))
            r = write_report(run_results, run_dir)
            all_metrics.append(r["metrics"])
            print(r["text"])
        accuracies = [m.accuracy for m in all_metrics]
        lines = [
            f"SC-01 — sebaran {a.repeat} run", "=" * 60,
            f"akurasi terendah : {min(accuracies):.1%}",
            f"akurasi tertinggi: {max(accuracies):.1%}",
            f"rata-rata        : {sum(accuracies)/len(accuracies):.1%}",
            f"rentang          : {(max(accuracies)-min(accuracies))*100:.1f} poin persen",
            f"baseline         : {all_metrics[0].baseline:.1%} ({all_metrics[0].majority_label})",
        ]
        text = "\n".join(lines)
        (out / "spread.txt").write_text(text, encoding="utf-8")
        print("\n" + text)
        return 0

    results = asyncio.run(run_pairs(pairs, cfg.images_dir(),
                                    out / "results_per_row.csv", a.restart))
    r = write_report(results, out)
    print("\n" + r["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
