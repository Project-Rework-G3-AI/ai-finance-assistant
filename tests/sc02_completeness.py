"""SC-02: kelengkapan field wajib pada hasil ekstraksi.

Kriteria ini hanya bertanya satu hal: **apakah field wajibnya terbaca**. Apakah
nilainya benar bukan urusan SC-02 — kecocokan isi diukur di SC-01 untuk kategori,
dan tidak diukur di sini untuk field lain.

Pemisahan itu disengaja. Kalau SC-02 ikut menilai kebenaran isi, satu field yang
merosot akan menyeret kriteria yang seharusnya mengukur hal lain, dan kegagalan
yang sama dilaporkan dua kali.

Jebakan utama modul ini ada di `main.extract`: fungsi itu mengisi nilai bawaan
secara diam-diam ketika model gagal membaca sesuatu.

    tanggal kosong -> tanggal hari ini
    arah kosong    -> "keluar"
    bank kosong    -> CR_DEFAULT_BANK

Kalau kelengkapan diukur dengan "field kosong atau tidak", hasilnya akan
mendekati 100% padahal model gagal membaca. Karena itu modul ini menilai
keterbacaan dari dua sumber:

  1. catatan  — `main.py` menulis "nominal tidak terbaca — isi manual" dan
                sejenisnya. Ini sinyal paling langsung, berasal dari kode yang
                tahu bedanya "model tidak menjawab" dan "model menjawab nilai".
  2. mode     — `mock` berarti model tidak dipanggil atau gagal, jadi tidak ada
                yang benar-benar terbaca. Nilainya dihitung sebagai gagal.

Nilai acuan dari dataset sengaja **tidak dipakai**. Membandingkan dengan acuan
adalah pengukuran kebenaran isi, bukan kelengkapan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Lima field wajib, sesuai skema kolom TRANSAKSI dan pesan di `main.py`.
REQUIRED_FIELDS = ("date", "amount", "bank", "direction", "category")

FIELD_LABELS = {
    "date": "tanggal",
    "amount": "nominal",
    "bank": "kantong",
    "direction": "arah",
    "category": "kategori",
}

# Potongan pesan di `main.py` yang menandakan field tidak terbaca. Dicocokkan
# longgar agar perubahan kecil pada kalimat tidak mematahkan pengukuran.
UNREADABLE_MARKERS = {
    "date": r"tanggal tidak terbaca",
    "amount": r"nominal tidak terbaca",
    "bank": r"kantong tidak terbaca",
    "category": r"kategori .*tidak (terbaca|dikenali)",
    "direction": r"arah tidak terbaca",
}


@dataclass
class FieldScore:
    """Hasil satu field pada seluruh set uji."""

    field: str
    total: int
    readable: int
    fallback: int

    @property
    def completeness(self) -> float:
        """Proporsi yang benar-benar terbaca, bukan hasil tebakan kode."""
        return self.readable / self.total if self.total else 0.0


@dataclass
class CompletenessResult:
    """Hasil SC-02 untuk satu run."""

    total: int
    fields: dict[str, FieldScore] = field(default_factory=dict)
    per_row: list[dict] = field(default_factory=list)

    @property
    def overall_completeness(self) -> float:
        """Rata-rata kelengkapan kelima field, bukan rata-rata per baris.

        Dihitung per field agar satu field yang sering gagal tidak tertutup
        oleh empat field yang selalu berhasil.
        """
        if not self.fields:
            return 0.0
        return sum(f.completeness for f in self.fields.values()) / len(self.fields)

    @property
    def all_fields_complete(self) -> int:
        """Jumlah baris yang kelima field wajibnya terbaca semua."""
        return sum(1 for r in self.per_row if r.get("complete") == "ya")

    def summary(self) -> str:
        lines = [
            f"total baris            : {self.total}",
            f"kelengkapan rata-rata  : {self.overall_completeness:.1%}",
            f"baris lengkap (5/5)    : {self.all_fields_complete}/{self.total}",
            "",
            f"{'field':12} {'terbaca':>9} {'kelengkapan':>12} {'tebakan':>8}",
        ]
        for name in REQUIRED_FIELDS:
            f = self.fields.get(name)
            if not f:
                continue
            lines.append(
                f"{FIELD_LABELS[name]:12} {f.readable:>4}/{f.total:<4} "
                f"{f.completeness:>11.1%} {f.fallback:>8}"
            )
        return "\n".join(lines)


def _is_unreadable(note: str, name: str) -> bool:
    """Apakah `catatan` menyebut field ini tidak terbaca.

    Diperiksa lebih dulu daripada nilai field, karena `main.py` sudah mengisi
    nilai bawaan pada saat ini — melihat nilainya saja akan menyesatkan.
    """
    pattern = UNREADABLE_MARKERS.get(name)
    if not pattern:
        return False
    return re.search(pattern, note or "", re.I) is not None


def score_row(record: dict) -> dict:
    """Nilai keterbacaan satu baris hasil ekstraksi.

    `record` memakai kunci Inggris hasil `sc_common.normalize_extract`.

    Nilai field **tidak** dibandingkan dengan acuan. Field yang terisi nilai
    salah tetap dihitung terbaca: SC-02 mengukur kelengkapan, bukan kebenaran.
    """
    note = str(record.get("remark") or "")
    mode = str(record.get("mode") or "")

    # Mode mock berarti model tidak benar-benar dipanggil atau gagal total.
    # Tidak ada field yang bisa dianggap terbaca dari model.
    mock = mode == "mock"

    readable: dict[str, bool] = {}
    fallback: dict[str, bool] = {}

    for name in REQUIRED_FIELDS:
        flagged = _is_unreadable(note, name)
        fallback[name] = flagged

        value = record.get(name)
        filled = value is not None and str(value).strip() != ""

        # Terbaca berarti: model dipanggil, tidak ada penanda gagal baca, dan
        # nilainya ada. Urutannya penting — `filled` saja tidak cukup karena
        # nilai bawaan juga membuat field tampak terisi.
        readable[name] = (not mock) and (not flagged) and filled

    return {
        "readable": readable,
        "fallback": fallback,
        "complete": "ya" if all(readable.values()) else "tidak",
        "mode": mode,
    }


def compute(rows: list[dict]) -> CompletenessResult:
    """Hitung SC-02 dari daftar baris yang sudah dinilai.

    Setiap elemen cukup memuat `record`; `reference` diabaikan bila ada, supaya
    pemanggil lama tidak perlu diubah.
    """
    if not rows:
        raise ValueError("tidak ada baris untuk dihitung")

    total = len(rows)
    counters = {
        name: {"readable": 0, "fallback": 0}
        for name in REQUIRED_FIELDS
    }
    per_row: list[dict] = []

    for item in rows:
        scored = score_row(item.get("record") or {})
        flat = {"file": item.get("file", ""), "mode": scored["mode"],
                "complete": scored["complete"]}
        for name in REQUIRED_FIELDS:
            if scored["readable"][name]:
                counters[name]["readable"] += 1
            if scored["fallback"][name]:
                counters[name]["fallback"] += 1
            flat[name] = "ya" if scored["readable"][name] else "tidak"
        per_row.append(flat)

    fields = {
        name: FieldScore(
            field=name,
            total=total,
            readable=c["readable"],
            fallback=c["fallback"],
        )
        for name, c in counters.items()
    }

    return CompletenessResult(total=total, fields=fields, per_row=per_row)
