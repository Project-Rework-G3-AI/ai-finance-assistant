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

    # 1. unduh gambar dataset (sekali saja, butuh GITHUB_TOKEN)
    python3 tests/sc01_harness.py --siapkan

    # 2. jalankan evaluasi (butuh AI_API_KEY)
    python3 tests/sc01_harness.py

    # 3. hitung ulang metrik dari CSV yang sudah ada (tanpa memanggil AI)
    python3 tests/sc01_harness.py --hitung-saja

Lokasi dataset diatur di `.env` lewat SC01_SET_UJI dan SC01_IMG_DIR.
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

AKAR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AKAR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc01_config as cfg  # noqa: E402

cfg.muat_env()

import httpx  # noqa: E402

from sc01_metrics import hitung  # noqa: E402

KOLOM_KELUARAN = [
    "file", "kategori_acuan", "kategori_usulan", "cocok",
    "nominal_acuan", "nominal_usulan", "selisih_nominal",
    "tanggal_acuan", "tanggal_usulan",
    "mode", "catatan", "keterangan_model", "detik",
]


def baca_hasil(path: Path) -> dict[str, dict]:
    """Hasil yang sudah ada, dipakai untuk melanjutkan run yang terputus."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {(r.get("file") or "").strip(): r for r in csv.DictReader(f)}


async def jalankan(pasangan: list[dict], img_dir: Path, out: Path,
                   ulang: bool = False) -> list[dict]:
    import main  # diimpor di dalam agar `--siapkan` tidak butuh AI_API_KEY

    sudah = {} if ulang else baca_hasil(out)
    hasil = list(sudah.values())

    belum = [p for p in pasangan if (p.get("file") or "").strip() not in sudah]
    if sudah:
        print(f"melanjutkan: {len(sudah)} sudah ada, {len(belum)} tersisa")
    if not belum:
        return hasil

    if not main.AI_KEY:
        raise SystemExit(
            "AI_API_KEY kosong. SC-01 mengukur akurasi model, jadi tidak bisa "
            "dijalankan dalam mode mock."
        )
    print(f"model: {main.AI_MODEL} via {main.AI_BASE}")
    print(f"gambar: {img_dir}\nkeluaran: {out}\n")

    # Tulis header lebih dulu agar file tetap valid walau proses mati di tengah.
    tulis_header = not out.exists()
    f = open(out, "a", encoding="utf-8", newline="")
    w = csv.DictWriter(f, fieldnames=KOLOM_KELUARAN, extrasaction="ignore")
    if tulis_header:
        w.writeheader()
        f.flush()

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i, p in enumerate(belum, 1):
            nama = (p.get("file") or "").strip()
            jalur = img_dir / nama
            if not jalur.exists():
                print(f"[{i}/{len(belum)}] LEWATI {nama}: file tidak ada")
                continue

            gambar = jalur.read_bytes()
            mulai = time.monotonic()
            try:
                rec = await main.extract(client, nama, gambar, "")
                galat = ""
            except Exception as e:
                rec = {"kategori": "", "nominal": None, "tanggal": "",
                       "mode": "error", "keterangan": "", "catatan": ""}
                galat = f"{type(e).__name__}: {e}"
            detik = time.monotonic() - mulai

            usulan = str(rec.get("kategori") or "").strip()
            acuan = (p.get("kategori_acuan") or "").strip()
            baris = {
                "file": nama,
                "kategori_acuan": acuan,
                "kategori_usulan": usulan,
                "cocok": "ya" if usulan == acuan else "tidak",
                "nominal_acuan": (p.get("nominal_acuan") or "").strip(),
                "nominal_usulan": rec.get("nominal"),
                "selisih_nominal": _selisih(p.get("nominal_acuan"), rec.get("nominal")),
                "tanggal_acuan": (p.get("tanggal") or "").strip(),
                "tanggal_usulan": rec.get("tanggal") or "",
                "mode": rec.get("mode") or ("error" if galat else ""),
                "catatan": (rec.get("catatan") or galat)[:300],
                "keterangan_model": (rec.get("keterangan") or "")[:200],
                "detik": round(detik, 2),
            }
            w.writerow(baris)
            f.flush()
            os.fsync(f.fileno())
            hasil.append(baris)

            tanda = "OK " if baris["cocok"] == "ya" else "SALAH"
            print(f"[{i}/{len(belum)}] {tanda} {nama[:38]:40} "
                  f"{usulan[:34]:36} ({detik:.1f}s)")

    f.close()
    return hasil


def _selisih(acuan, usulan) -> str:
    try:
        return str(int(float(acuan)) - int(float(usulan)))
    except (TypeError, ValueError):
        return ""


def tulis_laporan(hasil: list[dict], out: Path) -> dict:
    """Hitung metrik lalu tulis laporan teks + metrik.json ke disk."""
    pasangan = [{"kategori_acuan": r["kategori_acuan"],
                 "kategori_usulan": r["kategori_usulan"],
                 "file": r["file"]} for r in hasil if r.get("kategori_acuan")]
    h = hitung(pasangan)

    baris = [
        "SC-01 — Akurasi usulan kategori",
        "=" * 60,
        h.ringkas(),
        "",
        "Target BRD: minimal 85%",
        f"Status    : {'TERCAPAI' if h.akurasi >= 0.85 else 'BELUM TERCAPAI'}",
        "",
        "Per kategori (diurutkan dari yang paling sering muncul)",
        "-" * 60,
        f"{'kategori':46} {'acuan':>5} {'benar':>5} {'recall':>7}",
    ]
    for label, d in sorted(h.per_kategori.items(), key=lambda kv: -kv[1]["acuan"]):
        baris.append(f"{label[:46]:46} {d['acuan']:5} {d['benar']:5} "
                     f"{d['recall']:6.0%}")

    baris += ["", "Confusion matrix (baris = acuan, kolom = usulan)", "-" * 60]
    for a in h.confusion:
        untuk = ", ".join(f"{u}={n}" for u, n in
                          sorted(h.confusion[a].items(), key=lambda kv: -kv[1]))
        baris.append(f"{a[:44]:46} -> {untuk}")

    if h.salah:
        baris += ["", f"Baris yang salah ({len(h.salah)})", "-" * 60]
        for s in h.salah:
            baris.append(f"{s['file'][:44]:46} {s['acuan'][:26]:28} -> {s['usulan'][:28]}")

    teks = "\n".join(baris)
    (out / "laporan.txt").write_text(teks, encoding="utf-8")
    (out / "metrik.json").write_text(
        json.dumps({
            "total": h.total, "benar": h.benar, "akurasi": h.akurasi,
            "baseline": h.baseline, "baseline_label": h.baseline_label,
            "lift": h.lift, "macro_avg": h.macro_avg,
            "per_kategori": h.per_kategori, "confusion": h.confusion,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"hasil": h, "teks": teks}


def main_cli() -> int:
    ap = argparse.ArgumentParser(
        description="Runner evaluasi SC-01 (akurasi kategori)")
    ap.add_argument("--siapkan", action="store_true",
                    help="unduh gambar dataset dari repo privat, lalu berhenti")
    ap.add_argument("--set-uji", default="", help="timpa SC01_SET_UJI")
    ap.add_argument("--img-dir", default="", help="timpa SC01_IMG_DIR")
    ap.add_argument("--out", default="sc01-out", help="folder keluaran (default: sc01-out)")
    ap.add_argument("--ulang", action="store_true", help="abaikan hasil lama, proses dari awal")
    ap.add_argument("--hitung-saja", action="store_true", help="hitung metrik tanpa memanggil AI")
    a = ap.parse_args()

    # Argumen CLI menang atas .env, supaya bisa dipakai tanpa menyunting file.
    if a.set_uji:
        os.environ["SC01_SET_UJI"] = a.set_uji
    if a.img_dir:
        os.environ["SC01_IMG_DIR"] = a.img_dir

    if a.siapkan:
        folder = cfg.img_dir()
        if folder is None:
            raise SystemExit("SC01_IMG_DIR belum diisi. Contoh:\n"
                             "  --img-dir ./dataset/Bukti\\ Transaksi\\ Januari\\ 2026")
        print(f"mengunduh gambar ke: {folder}")
        baru, lewat = cfg.unduh_gambar(folder)
        print(f"selesai: {baru} diunduh, {lewat} sudah ada")
        siap, alasan = cfg.siap(abaikan_ai=True)
        print(f"status: {'siap' if siap else 'BELUM siap'} — {alasan}")
        return 0 if siap else 1

    out = Path(a.out)
    if not out.is_absolute():
        out = AKAR / out
    out.mkdir(parents=True, exist_ok=True)

    if a.hitung_saja:
        hasil = list(baca_hasil(out / "hasil_per_baris.csv").values())
        if not hasil:
            raise SystemExit(f"tidak ada hasil di {out / 'hasil_per_baris.csv'}")
        r = tulis_laporan(hasil, out)
        print(r["teks"])
        return 0

    siap, alasan = cfg.siap()
    if not siap:
        raise SystemExit(f"belum siap: {alasan}")

    pasangan = cfg.baca_pasangan(cfg.set_uji())
    print(f"pasangan: {len(pasangan)}")
    hasil = asyncio.run(jalankan(pasangan, cfg.img_dir(),
                                 out / "hasil_per_baris.csv", a.ulang))
    r = tulis_laporan(hasil, out)
    print("\n" + r["teks"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
