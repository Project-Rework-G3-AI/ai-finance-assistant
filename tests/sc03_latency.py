"""SC-03: waktu proses dari bukti diterima sampai hasilnya tersimpan.

Target BRD: < 5 detik.

Dua definisi, keduanya diukur dan dilaporkan terpisah:

- `stored`  — sampai baris benar-benar masuk ke Google Sheets. Ini definisi
  dokumen, dan ini yang dipakai menilai target.
- `replied` — sampai balasan Telegram terkirim. Ini definisi yang dipakai
  pengguna saat berbicara, lebih ketat karena menambah perjalanan pulang-pergi.

Rantai yang diukur, dengan nama tahapnya:

    terima -> extract (AI) -> dedupe (Sheets baca) -> upload (Drive)
           -> append (Sheets tulis) -> reply (Telegram)

Modul ini **tidak** memanggil Telegram sungguhan. Balasan diukur sebagai
panggilan HTTP ke Bot API yang di-mock: yang diukur adalah waktu menyusun dan
mengirim permintaan, bukan waktu Telegram memproses. Untuk SC-03 itu memadai,
karena target BRD berhenti di "tersimpan" dan bagian Telegram hanya angka
tambahan. Batas ini dicetak di laporan supaya tidak disalahartikan.

Waktu tidak bisa dihitung ulang dari CSV. Berbeda dari SC-01/SC-02, kriteria ini
hanya bisa diukur saat kejadian berlangsung.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

TARGET_SECONDS = 5.0

# Tahap yang diukur, berurutan sesuai rantai sebenarnya.
STAGES = ("extract", "dedupe", "upload", "append", "reply")


@dataclass
class Sample:
    """Satu pengukuran untuk satu gambar."""

    file: str
    stages: dict[str, float] = field(default_factory=dict)
    ok: bool = True
    error: str = ""

    @property
    def stored(self) -> float:
        """Sampai tersimpan: terima -> extract -> dedupe -> upload -> append.

        `reply` sengaja tidak dijumlahkan: definisi BRD berhenti di tersimpan.
        """
        return sum(self.stages.get(s, 0.0) for s in ("extract", "dedupe", "upload", "append"))

    @property
    def replied(self) -> float:
        """Sampai balasan terkirim: `stored` ditambah tahap reply.

        Hanya bermakna bila tahap reply benar-benar dijalankan. Saat di-mock,
        nilainya sama dengan `stored` dan laporan harus menyebutnya tidak diukur.
        """
        return self.stored + self.stages.get("reply", 0.0)


def _stats(values: list[float]) -> dict:
    """Ringkasan sebaran. Persentil dipakai karena satu baris bisa sangat lambat."""
    if not values:
        return {"n": 0, "mean": 0.0, "median": 0.0, "p90": 0.0, "max": 0.0, "min": 0.0}
    ordered = sorted(values)
    n = len(ordered)
    # Persentil 90 dengan interpolasi sederhana; cukup untuk 65 sampel.
    idx = min(n - 1, int(round(0.9 * (n - 1))))
    return {
        "n": n,
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p90": ordered[idx],
        "max": ordered[-1],
        "min": ordered[0],
    }


def compute(samples: list[Sample], target: float = TARGET_SECONDS,
            reply_measured: bool = False) -> dict:
    """Hitung ringkasan SC-03 dari daftar sampel.

    `reply_measured` harus False bila tahap reply hanya di-mock. Angka 0,00
    detik akan terbaca sebagai "Telegram instan", padahal yang terjadi adalah
    tahap itu tidak pernah dijalankan sungguhan.
    """
    used = [s for s in samples if s.ok]
    failed = [s for s in samples if not s.ok]

    stored = [s.stored for s in used]
    replied = [s.replied for s in used]

    over_target = [s for s in used if s.stored > target]

    return {
        "target_seconds": target,
        "total": len(samples),
        "measured": len(used),
        "failed": len(failed),
        "failed_files": [s.file for s in failed],
        "stored": _stats(stored),
        "replied": _stats(replied) if reply_measured else None,
        "reply_measured": reply_measured,
        "over_target": len(over_target),
        "over_target_files": [s.file for s in over_target],
        "stages": {name: _stats([s.stages.get(name, 0.0) for s in used])
                   for name in STAGES},
        # Dipakai menilai target: rata-rata `stored`, sesuai definisi dokumen.
        "mean_stored": statistics.fmean(stored) if stored else 0.0,
        "pass": bool(stored) and statistics.fmean(stored) <= target,
    }


def verdict(c: dict) -> str:
    return "TERCAPAI" if c["pass"] else "BELUM TERCAPAI"


def report(c: dict, source_note: str = "") -> str:
    """Teks laporan SC-03, siap ditulis ke `sc03_report.txt`."""
    row = [
        "SC-03 — Waktu proses sampai tersimpan",
        "=" * 60,
    ]
    if source_note:
        row += [source_note, ""]

    row += [
        f"Target BRD         : kurang dari {c['target_seconds']:.0f} detik",
        f"Angka yang dinilai : rata-rata waktu sampai tersimpan "
        f"{c['mean_stored']:.2f} detik ({c['measured']} gambar)  <- dibandingkan dengan target",
        f"Status             : {verdict(c)}",
        "",
        "Angka lain (tidak dipakai menilai target)",
        "-" * 60,
        (f"  {'sampai balasan Telegram':31}: {c['replied']['mean']:.2f} detik  "
         f"definisi pengguna, lebih ketat"
         if c.get("reply_measured") else
         f"  {'sampai balasan Telegram':31}: tidak diukur — Telegram di-mock, "
         f"jadi tidak ada perjalanan pulang-pergi nyata"),
        f"  {'median sampai tersimpan':31}: {c['stored']['median']:.2f} detik  "
        f"separuh gambar lebih cepat dari ini",
        f"  {'persentil 90':31}: {c['stored']['p90']:.2f} detik  "
        f"10% gambar lebih lambat dari ini",
        "",
        "Sebaran waktu sampai tersimpan",
        "-" * 60,
        f"  jumlah gambar      : {c['measured']}",
        f"  rata-rata          : {c['stored']['mean']:.2f} detik",
        f"  median             : {c['stored']['median']:.2f} detik",
        f"  persentil 90       : {c['stored']['p90']:.2f} detik",
        f"  tercepat           : {c['stored']['min']:.2f} detik",
        f"  terlambat          : {c['stored']['max']:.2f} detik",
        f"  lewat {c['target_seconds']:.0f} detik      : {c['over_target']} dari {c['measured']} gambar",
        "",
        "Waktu per tahap (rata-rata)",
        "-" * 60,
    ]
    for name in STAGES:
        s = c["stages"][name]
        if name == "reply" and not c.get("reply_measured"):
            row.append(f"  {name:18}: tidak diukur (Telegram di-mock)")
        else:
            row.append(f"  {name:18}: {s['mean']:.2f} detik  (median {s['median']:.2f})")

    if c["failed"]:
        row += [
            "",
            f"Gagal diukur: {c['failed']} gambar",
            "-" * 60,
        ]
        row += [f"  {n}" for n in c["failed_files"][:10]]

    return "\n".join(row) + "\n"


def write_report(c: dict, out: Path, source_note: str = "") -> dict:
    """Tulis `sc03_report.txt` dan `sc03_metrics.json`."""
    import json

    text = report(c, source_note)
    (out / "sc03_report.txt").write_text(text, encoding="utf-8")
    (out / "sc03_metrics.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return c


class Timer:
    """Pengukur sederhana, dipakai sebagai context manager per tahap."""

    def __init__(self, sample: Sample):
        self.sample = sample
        self._t0 = 0.0

    def __call__(self, stage: str):
        return _Stage(self.sample, stage)


class _Stage:
    def __init__(self, sample: Sample, stage: str):
        self.sample = sample
        self.stage = stage

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.sample.stages[self.stage] = time.perf_counter() - self._t0
        return False
