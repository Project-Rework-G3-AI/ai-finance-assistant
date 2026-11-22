"""Perhitungan metrik SC-01.

Modul ini sengaja tidak memanggil AI dan tidak menyentuh Google. Tugasnya hanya
mengubah daftar pasangan (kategori acuan vs kategori usulan) menjadi angka yang
bisa dipertanggungjawabkan di laporan.

Tiga angka dilaporkan bersamaan, karena satu angka saja menyesatkan:

  akurasi     benar / total. Bisa terlihat bagus hanya karena kelas mayoritas.
  baseline    proporsi kelas terbanyak pada data uji. Batas bawah yang harus
              dilewati model agar dianggap belajar, bukan menebak.
  macro-avg   rata-rata recall per kategori. Setiap kategori berbobot sama,
              sehingga kategori jarang tidak tertutup oleh kategori mayoritas.

Selisih akurasi terhadap baseline disebut lift. Lift negatif berarti model kalah
dari tebakan konstan, sekalipun akurasinya terlihat tinggi.

Selain itu dihitung pula confusion matrix, presisi/recall/F1 per kategori, dan
jumlah kategori yang tidak dikenali kode (masuk PERLU_DITINJAU), karena kesalahan
jenis itu berbeda artinya dari salah pilih kategori yang sah.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class Hasil:
    """Hasil perhitungan satu run evaluasi."""

    total: int
    benar: int
    akurasi: float
    baseline: float
    baseline_label: str
    lift: float
    macro_avg: float
    per_kategori: dict[str, dict] = field(default_factory=dict)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    salah: list[dict] = field(default_factory=list)

    def ringkas(self) -> str:
        """Ringkasan satu blok teks untuk laporan."""
        baris = [
            f"total pasangan      : {self.total}",
            f"benar               : {self.benar}",
            f"akurasi             : {self.akurasi:.1%}",
            f"baseline (mayoritas): {self.baseline:.1%}  ({self.baseline_label})",
            f"lift atas baseline  : {self.lift:+.1%}",
            f"macro-average recall: {self.macro_avg:.1%}",
        ]
        return "\n".join(baris)


def _bagi(a: int, b: int) -> float:
    return a / b if b else 0.0


def hitung(pasangan: list[dict], kunci_acuan: str = "kategori_acuan",
           kunci_usulan: str = "kategori_usulan") -> Hasil:
    """Hitung seluruh metrik dari daftar pasangan.

    Setiap elemen minimal memuat dua kunci: kategori acuan (yang ditetapkan
    Admin) dan kategori usulan (keluaran sistem).
    """
    if not pasangan:
        raise ValueError("daftar pasangan kosong — tidak ada yang bisa dihitung")

    acuan = [str(p[kunci_acuan]).strip() for p in pasangan]
    usulan = [str(p[kunci_usulan]).strip() for p in pasangan]

    total = len(pasangan)
    benar = sum(1 for a, u in zip(acuan, usulan) if a == u)

    sebaran = Counter(acuan)
    label_mayoritas, n_mayoritas = sebaran.most_common(1)[0]
    baseline = _bagi(n_mayoritas, total)
    akurasi = _bagi(benar, total)

    # Recall per kategori acuan. Kategori yang tidak muncul di data uji tidak
    # dihitung — membaginya dengan nol akan menyeret macro-average ke bawah
    # tanpa alasan yang bisa dipertanggungjawabkan.
    recall: dict[str, float] = {}
    presisi: dict[str, float] = {}
    f1: dict[str, float] = {}
    per_kategori: dict[str, dict] = {}

    for label, jumlah in sebaran.items():
        kena = sum(1 for a, u in zip(acuan, usulan) if a == label and u == label)
        recall[label] = _bagi(kena, jumlah)

        usulan_label = sum(1 for u in usulan if u == label)
        presisi[label] = _bagi(kena, usulan_label)

        r, p = recall[label], presisi[label]
        f1[label] = _bagi(2 * p * r, p + r)

        per_kategori[label] = {
            "acuan": jumlah,
            "benar": kena,
            "recall": r,
            "presisi": p,
            "f1": f1[label],
            "usulan": usulan_label,
        }

    macro_avg = _bagi(sum(recall.values()), len(recall)) if recall else 0.0

    confusion: dict[str, dict[str, int]] = defaultdict(dict)
    for a, u in zip(acuan, usulan):
        confusion[a][u] = confusion[a].get(u, 0) + 1

    salah = [
        {"acuan": a, "usulan": u, **{k: v for k, v in p.items()
                                     if k not in (kunci_acuan, kunci_usulan)}}
        for a, u, p in zip(acuan, usulan, pasangan) if a != u
    ]

    return Hasil(
        total=total,
        benar=benar,
        akurasi=akurasi,
        baseline=baseline,
        baseline_label=label_mayoritas,
        lift=akurasi - baseline,
        macro_avg=macro_avg,
        per_kategori=per_kategori,
        confusion={k: dict(v) for k, v in confusion.items()},
        salah=salah,
    )
