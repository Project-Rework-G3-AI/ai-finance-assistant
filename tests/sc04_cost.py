"""SC-04: biaya per gambar, dihitung dari token yang benar-benar terpakai.

Target BRD: **di bawah Rp50 per gambar**.

Biaya satu gambar:

    (token prompt x tarif prompt) + (token completion x tarif completion) x kurs

## Menyesuaikan tarif dan kurs

Tarif berubah, kurs berubah, dan model bisa diganti. Karena itu **tidak ada
angka tarif yang tertanam di kode**. Urutan penentuan, dari yang paling menang:

1. Argumen CLI      `--price-prompt`, `--price-completion`, `--usd-idr`, `--target-idr`
2. Variabel env     `SC04_PRICE_PROMPT_USD`, `SC04_PRICE_COMPLETION_USD`,
                    `SC04_USD_IDR`, `SC04_TARGET_IDR`
3. Katalog penyedia diambil saat mengukur, supaya tarif tidak basi
4. Bila ketiganya tidak ada, berhenti dengan pesan jelas

Contoh menyesuaikan tanpa menyunting kode:

    python3 tests/_sc04_run.py --price-prompt 0.00000015 --price-completion 0.0000006
    python3 tests/_sc04_run.py --usd-idr 18227
    SC04_TARGET_IDR=40 python3 tests/_sc04_run.py

Dua hal yang sengaja tidak dilakukan:

- **Token tidak ditebak dari panjang teks.** Jumlah token diambil dari field
  `usage` pada respons penyedia. Menaksir token dari jumlah karakter menghasilkan
  biaya yang terlihat masuk akal tetapi tidak benar.
- **Tarif tidak disimpan sebagai konstanta.** Tarif yang tertanam di kode akan
  jadi bohong tanpa ada yang sadar saat penyedia menaikkan harga.
"""

from __future__ import annotations

import json
import os
import statistics
from dataclasses import dataclass
from pathlib import Path

# =====================================================================
# VARIABEL PERHITUNGAN — ubah di sini untuk menyesuaikan biaya
# =====================================================================
#
# Tiga nilai di bawah adalah MASUKAN perhitungan, bukan hasil. Mengubahnya
# mengubah biaya yang dilaporkan. Hasil hitung tidak pernah disimpan, selalu
# diturunkan ulang dari token dan nilai-nilai ini.
#
# Urutan siapa yang menang, dari yang paling kuat:
#   1. Argumen CLI   --price-prompt / --price-completion / --usd-idr / --target-idr
#   2. Variabel env  SC04_PRICE_PROMPT_USD / SC04_PRICE_COMPLETION_USD /
#                    SC04_USD_IDR / SC04_TARGET_IDR
#   3. Variabel di bawah ini (nilai bawaan)
#   4. Katalog penyedia, hanya bila tarif tidak diisi sama sekali
#
# Jadi mengubah angka di bawah berlaku untuk semua orang yang menjalankan test
# ini, sementara CLI/env menimpanya untuk satu kali jalan tanpa menyunting kode.

# ---------------------------------------------------------------------
# TARIF MODEL — ubah angka di sini untuk menyesuaikan biaya
# ---------------------------------------------------------------------
# Kita memakai satu model. Cukup sunting dua angka di bawah: tarif dalam USD
# per token, sesuai harga penyedia untuk model di AI_MODEL.
#
# Acuan saat ini, deepseek/deepseek-v4.1-flash-1017 di OpenRouter:
#     prompt     $0.00000015 / token
#     completion $0.0000006  / token
#
# Kalau penyedia mengubah harga, ubah dua angka ini. Seluruh laporan ikut
# berubah, karena biaya selalu dihitung ulang dari token x tarif x kurs.
PRICE_PROMPT_USD = 0.00000015
PRICE_COMPLETION_USD = 0.0000006

# Kurs rupiah per USD. 0.0 berarti "belum diisi" -> wajib lewat CLI atau env,
# karena kurs tidak ditebak: ia mengubah hasil secara langsung.
USD_TO_IDR = 0.0

# Target BRD: di bawah Rp50 per gambar.
TARGET_IDR = 50.0

# Nama variabel lingkungan yang dibaca. Didaftar di satu tempat supaya pesan
# bantuan dan pembacaan tidak bisa berbeda pendapat.
ENV_PROMPT = "SC04_PRICE_PROMPT_USD"
ENV_COMPLETION = "SC04_PRICE_COMPLETION_USD"
ENV_USD_IDR = "SC04_USD_IDR"
ENV_TARGET = "SC04_TARGET_IDR"
ENV_MODEL = "AI_MODEL"


@dataclass
class Pricing:
    """Tarif satu model, dalam USD per token."""

    model: str
    prompt_usd: float
    completion_usd: float
    source: str = ""

    def cost_usd(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Biaya satu panggilan dalam USD."""
        return (prompt_tokens * self.prompt_usd
                + completion_tokens * self.completion_usd)


@dataclass
class Sample:
    """Satu gambar: token yang terpakai dan biayanya."""

    file: str
    ok: bool = True
    error: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_idr: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _dari_env(nama: str) -> str:
    return (os.getenv(nama) or "").strip()


def target_from(override: float | None = None) -> float:
    """Target rupiah per gambar.

    Urutan: argumen CLI, lalu env, lalu variabel `TARGET_IDR` di berkas ini.
    """
    if override is not None:
        return float(override)
    mentah = _dari_env(ENV_TARGET)
    if mentah:
        try:
            return float(mentah)
        except ValueError:
            raise SystemExit(
                f"{ENV_TARGET} harus berupa angka, bukan {mentah!r}")
    return TARGET_IDR


def usd_to_idr_from(override: float | None = None) -> float:
    """Kurs rupiah per USD.

    Urutan: argumen CLI, lalu env, lalu variabel `USD_TO_IDR` di berkas ini.
    Nilai 0 berarti belum diisi dan pemanggil wajib memberi tahu pengguna,
    karena kurs mengubah hasil secara langsung.
    """
    if override is not None:
        return float(override)
    mentah = _dari_env(ENV_USD_IDR)
    if mentah:
        try:
            return float(mentah)
        except ValueError:
            raise SystemExit(
                f"{ENV_USD_IDR} harus berupa angka, bukan {mentah!r}")
    return USD_TO_IDR


def pricing_from(prompt: float | None = None, completion: float | None = None,
                 model: str | None = None,
                 catalog: dict | None = None) -> Pricing:
    """Tentukan tarif yang dipakai.

    `catalog` adalah entri katalog penyedia (bentuk OpenRouter) yang dipakai bila
    tarif tidak diberikan lewat CLI maupun env. Bila semuanya kosong, berhenti:
    menebak tarif berarti melaporkan biaya yang tidak bisa dipertanggungjawabkan.
    """
    nama_model = (model or _dari_env(ENV_MODEL) or "").strip()

    # 1. CLI
    if prompt is not None and completion is not None:
        return Pricing(model=nama_model or "(ditentukan manual)",
                       prompt_usd=float(prompt),
                       completion_usd=float(completion),
                       source="argumen CLI")

    # 2. env
    env_p = _dari_env(ENV_PROMPT)
    env_c = _dari_env(ENV_COMPLETION)
    if prompt is None and completion is None and env_p and env_c:
        try:
            return Pricing(model=nama_model or "(ditentukan manual)",
                           prompt_usd=float(env_p),
                           completion_usd=float(env_c),
                           source=f"variabel lingkungan {ENV_PROMPT}/{ENV_COMPLETION}")
        except ValueError:
            raise SystemExit(
                f"{ENV_PROMPT} dan {ENV_COMPLETION} harus berupa angka.")

    # 3. tarif umum di kode (PRICE_PROMPT_USD / PRICE_COMPLETION_USD)
    if prompt is None and completion is None:
        if PRICE_PROMPT_USD and PRICE_COMPLETION_USD:
            return Pricing(model=nama_model or "(ditentukan manual)",
                           prompt_usd=float(PRICE_PROMPT_USD),
                           completion_usd=float(PRICE_COMPLETION_USD),
                           source="variabel PRICE_*_USD di tests/sc04_cost.py")

    # Setengah diisi: jangan diam-diam mencampur sumber yang berbeda.
    if (prompt is None) != (completion is None):
        raise SystemExit(
            "Tarif prompt dan completion harus diberikan bersama. "
            "Isi keduanya, atau biarkan kosong dan pakai katalog penyedia.")
    if bool(env_p) != bool(env_c):
        raise SystemExit(
            f"{ENV_PROMPT} dan {ENV_COMPLETION} harus diisi bersama.")

    # 4. katalog penyedia
    if catalog:
        harga = catalog.get("pricing", {})
        try:
            return Pricing(model=catalog.get("id", nama_model),
                           prompt_usd=float(harga["prompt"]),
                           completion_usd=float(harga["completion"]),
                           source="katalog OpenRouter saat pengukuran")
        except (KeyError, TypeError, ValueError):
            raise SystemExit(
                f"Katalog tidak memuat tarif lengkap untuk {nama_model!r}. "
                "Isi --price-prompt dan --price-completion secara manual.")

    raise SystemExit(
        "Tarif belum diketahui. Pilih salah satu:\n"
        "  --price-prompt <usd/token> --price-completion <usd/token>\n"
        f"  {ENV_PROMPT}=... {ENV_COMPLETION}=...\n"
        "  isi PRICE_PROMPT_USD dan PRICE_COMPLETION_USD di tests/sc04_cost.py\n"
        "  atau jalankan dengan akses katalog penyedia supaya tarif diambil otomatis.")


def cost_idr(pricing: Pricing, prompt_tokens: int, completion_tokens: int,
             usd_to_idr: float) -> float:
    """Biaya satu gambar dalam rupiah."""
    return pricing.cost_usd(prompt_tokens, completion_tokens) * usd_to_idr


def _stats(nilai: list[float]) -> dict:
    """Ringkasan sebaran. Persentil dihitung dengan interpolasi linear."""
    if not nilai:
        return {"n": 0, "mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0,
                "p90": 0.0}
    urut = sorted(nilai)

    def persen(p: float) -> float:
        if len(urut) == 1:
            return urut[0]
        pos = (len(urut) - 1) * p
        bawah = int(pos)
        atas = min(bawah + 1, len(urut) - 1)
        return urut[bawah] + (urut[atas] - urut[bawah]) * (pos - bawah)

    return {
        "n": len(nilai),
        "mean": statistics.fmean(nilai),
        "median": statistics.median(nilai),
        "min": urut[0],
        "max": urut[-1],
        "p90": persen(0.9),
    }


def compute(samples: list[Sample], target: float = TARGET_IDR,
            pricing: Pricing | None = None,
            usd_to_idr: float = 0.0) -> dict:
    """Ringkas biaya per gambar.

    Sampel yang gagal diukur tidak masuk rata-rata. Biaya Rp0 untuk gambar yang
    gagal akan terbaca sebagai "gratis", padahal yang terjadi adalah tidak ada
    data.
    """
    berhasil = [s for s in samples if s.ok]

    # Biaya SELALU diturunkan dari token x tarif x kurs, bukan dibaca dari
    # `s.cost_idr` yang mungkin sudah terisi. Kalau membaca nilai jadi, mengubah
    # tarif atau kurs tidak akan berefek pada angka yang sudah ada, dan
    # penyesuaian tarif yang diminta jadi sia-sia. `s.cost_idr` hanya dipakai
    # sebagai cadangan bila tarif memang tidak diberikan.
    if pricing is not None and usd_to_idr:
        biaya = [cost_idr(pricing, s.prompt_tokens, s.completion_tokens,
                          usd_to_idr) for s in berhasil]
        for s, b in zip(berhasil, biaya):
            s.cost_idr = b
    else:
        biaya = [s.cost_idr for s in berhasil]

    hasil = {
        "measured": len(berhasil),
        "failed": len(samples) - len(berhasil),
        "target_idr": target,
        "mean_idr": statistics.fmean(biaya) if biaya else 0.0,
        "cost": _stats(biaya),
        "prompt_tokens": _stats([float(s.prompt_tokens) for s in berhasil]),
        "completion_tokens": _stats([float(s.completion_tokens) for s in berhasil]),
        "total_tokens": _stats([float(s.total_tokens) for s in berhasil]),
        "over_target": sum(1 for x in biaya if x > target),
        "usd_to_idr": usd_to_idr,
    }
    if pricing:
        hasil["pricing"] = {
            "model": pricing.model,
            "prompt_usd_per_token": pricing.prompt_usd,
            "completion_usd_per_token": pricing.completion_usd,
            "source": pricing.source,
        }
    # Nol pengukuran bukan hasil; jangan pernah dianggap lulus.
    hasil["pass"] = bool(biaya) and hasil["mean_idr"] <= target
    return hasil


def verdict(c: dict) -> str:
    """Status terhadap target, atau alasan bila tidak bisa dinilai."""
    if not c.get("measured"):
        return "BELUM DIUKUR"
    return "TERCAPAI" if c.get("pass") else "BELUM TERCAPAI"


def report(c: dict, source: str = "") -> str:
    """Laporan teks SC-04.

    Status selalu didahului angka yang dinilai dan penyebutnya, sama seperti
    kriteria lain. Tanpa itu, pembaca melihat beberapa angka dan satu status
    tanpa tahu mana yang menentukan.
    """
    baris = ["SC-04 — Biaya per gambar", "=" * 60]
    if source:
        baris.append(source)
    baris.append("")

    if not c.get("measured"):
        baris += [
            f"Status             : {verdict(c)}",
            "",
            "Belum ada sampel biaya. Jalankan pengukuran lebih dulu:",
            "",
            "  python3 tests/_sc04_run.py",
        ]
        return "\n".join(baris)

    harga = c.get("pricing", {})
    baris += [
        f"Target             : di bawah Rp{c['target_idr']:.2f} per gambar",
        f"Angka yang dinilai : rata-rata biaya per gambar Rp{c['mean_idr']:.2f} "
        f"({c['measured']} gambar)  <- dibandingkan dengan target",
        f"Status             : {verdict(c)}",
        "",
        "Tarif yang dipakai",
        "-" * 60,
        f"  model              : {harga.get('model', '(tidak dicatat)')}",
    ]
    if harga:
        baris += [
            f"  prompt             : ${harga['prompt_usd_per_token']:.10f} / token",
            f"  completion         : ${harga['completion_usd_per_token']:.10f} / token",
        ]
    baris.append(f"  kurs               : Rp{c['usd_to_idr']:.2f} per USD")
    if harga.get("source"):
        baris.append(f"  sumber tarif       : {harga['source']}")

    baris += [
        "",
        "Sebaran biaya per gambar",
        "-" * 60,
        f"  jumlah gambar      : {c['measured']}",
        f"  rata-rata          : Rp{c['cost']['mean']:.2f}",
        f"  median             : Rp{c['cost']['median']:.2f}",
        f"  persentil 90       : Rp{c['cost']['p90']:.2f}",
        f"  termurah           : Rp{c['cost']['min']:.2f}",
        f"  termahal           : Rp{c['cost']['max']:.2f}",
        f"  di atas target     : {c['over_target']} dari {c['measured']} gambar",
        "",
        "Token per gambar (rata-rata)",
        "-" * 60,
        f"  prompt             : {c['prompt_tokens']['mean']:.0f} token "
        f"(median {c['prompt_tokens']['median']:.0f})",
        f"  completion         : {c['completion_tokens']['mean']:.0f} token "
        f"(median {c['completion_tokens']['median']:.0f})",
        f"  total              : {c['total_tokens']['mean']:.0f} token "
        f"(median {c['total_tokens']['median']:.0f})",
    ]
    if c.get("failed"):
        baris += ["", f"Catatan: {c['failed']} gambar gagal diukur dan tidak "
                      "masuk rata-rata."]
    return "\n".join(baris)


def write_report(c: dict, out: Path, source: str = "") -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "sc04_report.txt").write_text(report(c, source), encoding="utf-8")
    (out / "sc04_metrics.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
