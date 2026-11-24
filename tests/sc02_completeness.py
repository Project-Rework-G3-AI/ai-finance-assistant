"""SC-02: kelengkapan field wajib pada hasil ekstraksi.

Yang diukur berbeda dari SC-01. SC-01 bertanya "apakah kategori yang dipilih
benar"; SC-02 bertanya "apakah field wajibnya terbaca". Sebuah model bisa
membaca tanggal, nominal, dan keterangan dengan tepat hampir selalu, tetapi
tetap salah memilih kategori. Karena itu hasil SC-01 yang rendah tidak
meramalkan hasil SC-02, dan keduanya harus dilaporkan terpisah.

Jebakan utama modul ini ada di `main.extract`: fungsi itu mengisi nilai bawaan
secara diam-diam ketika model gagal membaca sesuatu.

    tanggal kosong -> tanggal hari ini
    arah kosong    -> "keluar"
    bank kosong    -> CR_DEFAULT_BANK

Kalau kelengkapan diukur dengan "field kosong atau tidak", hasilnya akan
mendekati 100% padahal model gagal membaca. Karena itu modul ini menilai
keterbacaan dari tiga sumber, berurutan dari yang paling dapat dipercaya:

  1. catatan  — `main.py` menulis "nominal tidak terbaca — isi manual" dan
                sejenisnya. Ini sinyal paling langsung, berasal dari kode yang
                tahu bedanya "model tidak menjawab" dan "model menjawab nilai".
  2. mode     — `mock` berarti model tidak dipanggil atau gagal, jadi tidak ada
                yang benar-benar terbaca. Nilainya dihitung sebagai gagal.
  3. acuan    — bila nilai acuan tersedia, hasil dibandingkan langsung. Ini
                yang membedakan "terbaca" dari "terbaca benar".

Untuk 65 baris di `sc_pairs.csv` kelima field punya acuan, sehingga bisa diukur
"terbaca benar". Untuk 118 gambar sisanya hanya "terisi" yang bisa diukur,
karena tidak ada nilai pembanding.
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

# Nilai bawaan yang dipakai `main.extract` saat model gagal membaca. Diperlukan
# untuk mendeteksi field yang "terisi" tetapi sebenarnya hasil tebakan kode.
FALLBACK_DIRECTION = "keluar"


@dataclass
class FieldScore:
    """Hasil satu field pada seluruh set uji."""

    field: str
    total: int
    readable: int
    correct: int
    fallback: int
    scored: int = 0

    @property
    def completeness(self) -> float:
        """Proporsi yang benar-benar terbaca, bukan hasil tebakan kode."""
        return self.readable / self.total if self.total else 0.0

    @property
    def accuracy(self) -> float:
        """Proporsi yang terbaca dan nilainya cocok, dari baris yang punya acuan.

        Penyebutnya `scored`, bukan `total`. Tanpa pemisahan ini, field tanpa
        acuan akan tampil 0% seolah selalu salah, padahal sebenarnya tidak
        dinilai. Angka seperti itu menyesatkan pembaca laporan.
        """
        return self.correct / self.scored if self.scored else 0.0

    @property
    def has_reference(self) -> bool:
        return self.scored > 0


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
    def overall_accuracy(self) -> float:
        """Rata-rata hanya dari field yang punya acuan."""
        scored = [f for f in self.fields.values() if f.has_reference]
        if not scored:
            return 0.0
        return sum(f.accuracy for f in scored) / len(scored)

    @property
    def scored_count(self) -> int:
        """Berapa field yang benar-benar ikut dirata-rata.

        Angka ini perlu disebut di laporan supaya pembaca tahu penyebut dari
        persentase yang dipakai menilai target. Tanpa itu, 72,5% bisa disangka
        rata-rata kelima field padahal hanya empat yang punya acuan.
        """
        return sum(1 for f in self.fields.values() if f.has_reference)

    def accuracy_excluding(self, *names: str) -> float:
        """Kecocokan rata-rata tanpa field tertentu.

        Dipakai untuk menunjukkan bahwa target gagal karena satu field saja.
        Kategori diukur di SC-01, jadi menyebut angkanya tanpa kategori
        membuat sebab kegagalan terbaca, bukan sekadar tersembunyi di rata-rata.
        """
        keep = [f for n, f in self.fields.items()
                if f.has_reference and n not in names]
        if not keep:
            return 0.0
        return sum(f.accuracy for f in keep) / len(keep)

    @property
    def all_fields_complete(self) -> int:
        """Jumlah baris yang kelima field wajibnya terbaca semua."""
        return sum(1 for r in self.per_row if r.get("complete") == "ya")

    def summary(self) -> str:
        lines = [
            f"total baris            : {self.total}",
            f"kelengkapan rata-rata  : {self.overall_completeness:.1%}",
            f"kecocokan rata-rata    : {self.overall_accuracy:.1%}",
            f"baris lengkap (5/5)    : {self.all_fields_complete}/{self.total}",
            "",
            f"{'field':12} {'terbaca':>9} {'kelengkapan':>12} {'cocok':>7} {'akurasi':>9} {'tebakan':>8}",
        ]
        for name in REQUIRED_FIELDS:
            f = self.fields.get(name)
            if not f:
                continue
            if f.has_reference:
                lines.append(
                    f"{FIELD_LABELS[name]:12} {f.readable:>4}/{f.total:<4} "
                    f"{f.completeness:>11.1%} {f.correct:>7} "
                    f"{f.accuracy:>8.1%} {f.fallback:>8}"
                )
            else:
                lines.append(
                    f"{FIELD_LABELS[name]:12} {f.readable:>4}/{f.total:<4} "
                    f"{f.completeness:>11.1%} {'-':>7} {'tidak dinilai':>13} "
                    f"{f.fallback:>8}"
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


def _used_fallback(record: dict, name: str, note: str) -> bool:
    """Apakah nilai field ini berasal dari nilai bawaan kode, bukan dari model."""
    if _is_unreadable(note, name):
        return True
    # Arah selalu punya nilai karena `main.py` memaksa "keluar". Tanpa penanda
    # di catatan, arah yang jatuh ke bawaan tidak bisa dibedakan dari arah yang
    # benar-benar terbaca — jadi hanya penanda catatan yang dipakai di sini.
    return False


def _normalize_amount(value) -> str:
    """Bandingkan nominal sebagai angka, bukan teks.

    Model kadang membalas "800353" dan acuan menyimpan "800353.0". Tanpa
    normalisasi, keduanya akan dianggap berbeda.
    """
    if value is None or str(value).strip() == "":
        return ""
    try:
        return str(int(float(str(value).replace(",", "").strip())))
    except (TypeError, ValueError):
        return str(value).strip()


def _normalize_text(value) -> str:
    return " ".join(str(value or "").split()).strip().lower()


def _normalize_date(value) -> str:
    """Ambil YYYY-MM-DD dari berbagai bentuk tanggal yang mungkin dibalas model."""
    s = str(value or "").strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return s


def score_row(record: dict, reference: dict | None = None) -> dict:
    """Nilai satu baris hasil ekstraksi.

    `record` memakai kunci Inggris hasil `sc_common.normalize_extract`.
    `reference` opsional; bila tidak ada, hanya keterbacaan yang bisa dinilai.
    """
    note = str(record.get("remark") or "")
    mode = str(record.get("mode") or "")
    reference = reference or {}

    # Mode mock berarti model tidak benar-benar dipanggil atau gagal total.
    # Tidak ada field yang bisa dianggap terbaca dari model.
    mock = mode == "mock"

    readable: dict[str, bool] = {}
    correct: dict[str, bool] = {}
    fallback: dict[str, bool] = {}

    for name in REQUIRED_FIELDS:
        flagged = _is_unreadable(note, name)
        fallback[name] = _used_fallback(record, name, note)

        value = record.get(name)
        filled = value is not None and str(value).strip() != ""

        # Terbaca berarti: model dipanggil, tidak ada penanda gagal baca, dan
        # nilainya ada. Urutannya penting — `filled` saja tidak cukup karena
        # nilai bawaan juga membuat field tampak terisi.
        readable[name] = (not mock) and (not flagged) and filled

        ref_value = reference.get(name)
        if ref_value is None or str(ref_value).strip() == "":
            # Tanpa acuan, kecocokan tidak bisa dinilai. Baris seperti ini tidak
            # dihitung sebagai benar maupun salah; lihat `reference_available`.
            correct[name] = False
            continue
        if not readable[name]:
            correct[name] = False
            continue

        if name == "amount":
            correct[name] = _normalize_amount(value) == _normalize_amount(ref_value)
        elif name == "date":
            correct[name] = _normalize_date(value) == _normalize_date(ref_value)
        else:
            correct[name] = _normalize_text(value) == _normalize_text(ref_value)

    has_reference = any(
        reference.get(n) not in (None, "") for n in REQUIRED_FIELDS
    )

    return {
        "readable": readable,
        "correct": correct,
        "fallback": fallback,
        "complete": "ya" if all(readable.values()) else "tidak",
        "reference_available": "ya" if has_reference else "tidak",
        "mode": mode,
    }


def compute(rows: list[dict]) -> CompletenessResult:
    """Hitung SC-02 dari daftar baris yang sudah dinilai.

    Setiap elemen memuat `record` dan `reference` (opsional). Hasil `score_row`
    dipakai ulang agar aturan penilaian hanya ada di satu tempat.
    """
    if not rows:
        raise ValueError("tidak ada baris untuk dihitung")

    total = len(rows)
    counters = {
        name: {"readable": 0, "correct": 0, "fallback": 0, "scored": 0}
        for name in REQUIRED_FIELDS
    }
    per_row: list[dict] = []

    for item in rows:
        scored = score_row(item.get("record") or {}, item.get("reference"))
        flat = {"file": item.get("file", ""), "mode": scored["mode"],
                "complete": scored["complete"],
                "reference_available": scored["reference_available"]}
        for name in REQUIRED_FIELDS:
            if scored["readable"][name]:
                counters[name]["readable"] += 1
            if scored["correct"][name]:
                counters[name]["correct"] += 1
            if scored["fallback"][name]:
                counters[name]["fallback"] += 1
            ref = (item.get("reference") or {}).get(name)
            if ref not in (None, ""):
                counters[name]["scored"] += 1
            flat[name] = "ya" if scored["readable"][name] else "tidak"
        per_row.append(flat)

    fields = {
        name: FieldScore(
            field=name,
            total=total,
            readable=c["readable"],
            correct=c["correct"],
            fallback=c["fallback"],
            scored=c["scored"],
        )
        for name, c in counters.items()
    }

    return CompletenessResult(total=total, fields=fields, per_row=per_row)
