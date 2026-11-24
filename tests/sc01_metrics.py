"""Perhitungan metrik SC-01.

Modul ini sengaja tidak memanggil AI dan tidak menyentuh Google. Tugasnya hanya
mengubah daftar pasangan (kategori acuan vs kategori usulan) menjadi angka yang
bisa dipertanggungjawabkan di laporan.

Tiga angka dilaporkan bersamaan, karena satu angka saja menyesatkan:

  accuracy    benar / total. Bisa terlihat bagus hanya karena kelas mayoritas.
  baseline    proporsi kelas terbanyak pada data uji. Batas bawah yang harus
              dilewati model agar dianggap belajar, bukan menebak.
  macro_avg   rata-rata recall per kategori. Setiap kategori berbobot sama,
              sehingga kategori jarang tidak tertutup oleh kategori mayoritas.

Selisih akurasi terhadap baseline disebut lift. Lift negatif berarti model kalah
dari tebakan konstan, sekalipun akurasinya terlihat tinggi.

Selain itu dihitung pula confusion matrix, presisi/recall/F1 per kategori, dan
jumlah kategori yang tidak dikenali kode, karena kesalahan jenis itu berbeda
artinya dari salah pilih kategori yang sah.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class Metrics:
    """Hasil perhitungan satu run evaluasi."""

    total: int
    correct: int
    accuracy: float
    baseline: float
    majority_label: str
    lift: float
    macro_avg: float
    per_category: dict[str, dict] = field(default_factory=dict)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    wrong: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        """Ringkasan satu blok teks untuk laporan."""
        lines = [
            f"total pasangan      : {self.total}",
            f"benar               : {self.correct}",
            f"akurasi             : {self.accuracy:.1%}",
            f"baseline (mayoritas): {self.baseline:.1%}  ({self.majority_label})",
            f"lift atas baseline  : {self.lift:+.1%}",
            f"macro-average recall: {self.macro_avg:.1%}",
        ]
        return "\n".join(lines)


def _ratio(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


def compute(pairs: list[dict], reference_key: str = "reference_category",
            proposed_key: str = "proposed_category") -> Metrics:
    """Hitung seluruh metrik dari daftar pasangan.

    Setiap elemen minimal memuat dua kunci: kategori acuan (yang ditetapkan
    Admin) dan kategori usulan (keluaran sistem).
    """
    if not pairs:
        raise ValueError("daftar pasangan kosong — tidak ada yang bisa dihitung")

    reference = [str(p[reference_key]).strip() for p in pairs]
    proposed = [str(p[proposed_key]).strip() for p in pairs]

    total = len(pairs)
    correct = sum(1 for a, u in zip(reference, proposed) if a == u)

    distribution = Counter(reference)
    majority_label, majority_count = distribution.most_common(1)[0]
    baseline = _ratio(majority_count, total)
    accuracy = _ratio(correct, total)

    # Recall per kategori acuan. Kategori yang tidak muncul di data uji tidak
    # dihitung — membaginya dengan nol akan menyeret macro-average ke bawah
    # tanpa alasan yang bisa dipertanggungjawabkan.
    recall: dict[str, float] = {}
    precision: dict[str, float] = {}
    f1: dict[str, float] = {}
    per_category: dict[str, dict] = {}

    for label, count in distribution.items():
        hits = sum(1 for a, u in zip(reference, proposed) if a == label and u == label)
        recall[label] = _ratio(hits, count)

        proposed_count = sum(1 for u in proposed if u == label)
        precision[label] = _ratio(hits, proposed_count)

        r, p = recall[label], precision[label]
        f1[label] = _ratio(2 * p * r, p + r)

        per_category[label] = {
            "reference": count,
            "correct": hits,
            "recall": r,
            "precision": p,
            "f1": f1[label],
            "proposed": proposed_count,
        }

    macro_avg = _ratio(sum(recall.values()), len(recall)) if recall else 0.0

    confusion: dict[str, dict[str, int]] = defaultdict(dict)
    for a, u in zip(reference, proposed):
        confusion[a][u] = confusion[a].get(u, 0) + 1

    wrong = [
        {"reference": a, "proposed": u, **{k: v for k, v in p.items()
                                          if k not in (reference_key, proposed_key)}}
        for a, u, p in zip(reference, proposed, pairs) if a != u
    ]

    return Metrics(
        total=total,
        correct=correct,
        accuracy=accuracy,
        baseline=baseline,
        majority_label=majority_label,
        lift=accuracy - baseline,
        macro_avg=macro_avg,
        per_category=per_category,
        confusion={k: dict(v) for k, v in confusion.items()},
        wrong=wrong,
    )
