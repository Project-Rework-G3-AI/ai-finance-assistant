"""SC-06: kelengkapan field yang diekstrak dari gambar.

Kriteria ini mengukur satu hal saja: ketika pengguna mengunggah gambar bukti
transaksi, apakah **seluruh field wajib benar-benar terbaca dari gambar**.

Yang sengaja **tidak** diukur di sini: apakah isinya benar. Nominal 20.000 yang
terbaca 50.000 tetap dihitung **terisi** — kecocokan nilai adalah urusan SC-01
dan SC-02, bukan kriteria ini.

Kenapa diukur dari balasan mentah model, bukan dari `main.extract()`:

    `main.extract()` tidak pernah mengembalikan field kosong. Tanggal kosong
    diganti `datetime.now()`, arah kosong dipaksa `"keluar"`, keterangan kosong
    diganti nama berkas, kantong kosong diganti `CR_DEFAULT_BANK`. Kalau yang
    diperiksa adalah hasil fungsi itu, semuanya akan selalu tampak lengkap dan
    kriteria ini tidak mengukur apa pun.

Jadi yang dibaca adalah balasan model sebelum dirapikan produksi. Selisih antara
keduanya dilaporkan terpisah sebagai "field yang ditutupi nilai bawaan", supaya
kegagalan ekstraksi tidak hilang diam-diam.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Field yang wajib terisi pada setiap gambar, apa pun arah transaksinya.
ALWAYS_REQUIRED = ("tanggal", "keterangan", "nominal", "arah", "kategori", "bank")

# Field yang hanya wajib ketika arah transaksinya transfer. Pada transaksi masuk
# atau keluar biasa, `kantong_tujuan` memang tidak punya nilai, jadi tidak boleh
# dihitung sebagai kekurangan.
CONDITIONAL_REQUIRED = ("kantong_tujuan",)


def is_required_for(name: str, raw: dict) -> bool:
    """Apakah field ini wajib terisi untuk transaksi ini."""
    if name in ALWAYS_REQUIRED:
        return True
    if name == "kantong_tujuan":
        return str((raw or {}).get("arah") or "").strip().lower() == "transfer"
    # Field baru yang muncul di prompt produksi tapi belum punya aturan di sini
    # dianggap wajib, supaya penambahan field tidak lolos tanpa diperhatikan.
    return True


def required_fields() -> list[str]:
    """Daftar field wajib, dibaca dari prompt produksi.

    Dibaca dari `main.py` supaya tidak ada daftar salinan yang bisa basi. Kalau
    produksi menambah atau mengganti field, daftar ini ikut berubah dan test
    yang membandingkannya dengan aturan penilaian akan gagal — itu memang
    tujuannya, karena field baru perlu diputuskan wajib atau tidak.
    """
    try:
        import main
    except Exception:
        return list(ALWAYS_REQUIRED) + list(CONDITIONAL_REQUIRED)

    teks = Path(main.__file__).read_text(encoding="utf-8")
    try:
        awal = teks.index("prompt = (")
        akhir = teks.index("if caption:", awal)
    except ValueError:
        return list(ALWAYS_REQUIRED) + list(CONDITIONAL_REQUIRED)

    # Prompt disusun dari literal string; jalankan potongan itu untuk mendapat
    # teks akhirnya, sama seperti yang dikirim ke model.
    ruang: dict = {}
    try:
        exec(teks[awal:akhir], {"KAT": main.KAT}, ruang)  # noqa: S102
        prompt = ruang["prompt"]
    except Exception:
        return list(ALWAYS_REQUIRED) + list(CONDITIONAL_REQUIRED)

    # Kunci JSON yang diminta dari model. Daftar kategori tidak memuat pola ini,
    # jadi tidak ikut tertangkap.
    import re

    return re.findall(r'"([a-z_]+)"\s*:', prompt)


# ---------------------------------------------------------------- penilaian


def field_is_filled(name: str, raw: dict) -> bool:
    """Apakah field ini benar-benar terisi di balasan model.

    Aturannya mengikuti cara produksi membaca field itu, supaya "terisi" berarti
    hal yang sama bagi test dan bagi aplikasi. Yang berbeda hanya satu: di sini
    nilai bawaan tidak dipakai, jadi field kosong tetap kosong.
    """
    raw = raw or {}
    value = raw.get(name)

    if name == "tanggal":
        import main

        _, valid = main._parse_tanggal_ke_datetime(value)
        return valid

    if name == "nominal":
        if value is None:
            return False
        teks = str(value).strip().replace(",", "").replace(".", "")
        if not teks:
            return False
        try:
            return int(float(str(value).replace(",", "").strip())) != 0
        except (TypeError, ValueError):
            return False

    if name == "arah":
        return str(value or "").strip().lower() in ("masuk", "keluar", "transfer")

    if name == "kategori":
        import main

        teks = str(value or "").strip()
        if not teks:
            return False
        return main.KAT.normalize(teks) != main.KAT.PERLU_DITINJAU

    # keterangan, bank, kantong_tujuan: cukup ada isinya. Keterangan sengaja
    # TIDAK memakai `_gabung_keterangan`, karena fungsi itu mengganti keterangan
    # kosong dengan nama berkas sehingga kegagalan model jadi tidak terlihat.
    return bool(str(value or "").strip())


# ------------------------------------------------------- apa yang ditutupi


class FakeResponse:
    """Balasan HTTP tiruan untuk memberi `main.extract` teks model tertentu."""

    def __init__(self, content: str):
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self._content}}]}


class FakeClient:
    """Klien HTTP tiruan yang selalu membalas dengan teks yang sama."""

    def __init__(self, content: str):
        self._content = content

    async def post(self, *args, **kwargs):
        return FakeResponse(self._content)


def through_production(raw: dict, filename: str, caption: str = "") -> dict:
    """Jalankan balasan model lewat `main.extract` yang asli, tanpa jaringan.

    Dipakai untuk melihat apa yang **diterima aplikasi** dari balasan yang sama.
    Perbedaannya dengan `field_is_filled` adalah field yang ditutupi nilai
    bawaan produksi.
    """
    import asyncio

    import main

    klien = FakeClient(json.dumps(raw, ensure_ascii=False))
    return asyncio.run(main.extract(klien, filename, b"tiruan", caption))


# ------------------------------------------------------------------ agregasi


@dataclass
class FieldScore:
    name: str
    filled: int = 0
    required: int = 0

    @property
    def rate(self) -> float:
        return (self.filled / self.required * 100.0) if self.required else 0.0


@dataclass
class ImageScore:
    file: str
    missing: list[str] = field(default_factory=list)
    covered: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def complete(self) -> bool:
        return not self.error and not self.missing


@dataclass
class Report:
    fields: list[FieldScore] = field(default_factory=list)
    images: list[ImageScore] = field(default_factory=list)
    required_names: list[str] = field(default_factory=list)

    @property
    def total_images(self) -> int:
        return len(self.images)

    @property
    def complete_images(self) -> int:
        return sum(1 for i in self.images if i.complete)

    @property
    def failed_images(self) -> int:
        return sum(1 for i in self.images if i.error)

    @property
    def complete_rate(self) -> float:
        dinilai = self.total_images - self.failed_images
        return (self.complete_images / dinilai * 100.0) if dinilai else 0.0

    @property
    def measured(self) -> int:
        return self.total_images - self.failed_images

    @property
    def covered_total(self) -> int:
        return sum(len(i.covered) for i in self.images)

    @property
    def pass_verdict(self) -> bool:
        # Target BRD: tidak ada field wajib yang hilang. Satu gambar saja yang
        # kehilangan satu field berarti target belum tercapai.
        return self.measured > 0 and self.complete_images == self.measured


def score_image(name: str, raw: dict, filename: str, caption: str = "") -> ImageScore:
    """Nilai satu gambar: field mana yang tidak terbaca dari balasan model."""
    hasil = ImageScore(file=name)
    for field_name in required_fields():
        if not is_required_for(field_name, raw):
            continue
        if not field_is_filled(field_name, raw):
            hasil.missing.append(field_name)

    # Field yang kosong di balasan model tetapi terisi setelah lewat produksi:
    # pengguna tidak melihatnya sebagai kosong, padahal isinya bukan dari gambar.
    if hasil.missing:
        diterima = through_production(raw, filename, caption)
        for field_name in hasil.missing:
            nilai = diterima.get(field_name)
            if str(nilai or "").strip():
                hasil.covered.append(field_name)
    return hasil


def compute(rows: list[dict]) -> Report:
    """Hitung laporan dari daftar baris berisi `file` dan `raw` (balasan model)."""
    laporan = Report(required_names=required_fields())
    per_field = {n: FieldScore(n) for n in laporan.required_names}

    for row in rows:
        name = str(row.get("file") or "")
        galat = str(row.get("error") or "").strip()
        raw = row.get("raw") or {}

        if galat:
            # Gambar yang gagal dipanggil tidak boleh dihitung lengkap, dan juga
            # tidak boleh dihitung sebagai bukti kelengkapan.
            laporan.images.append(ImageScore(file=name, error=galat))
            continue

        nilai = score_image(name, raw, name, str(row.get("caption") or ""))
        laporan.images.append(nilai)

        for field_name in laporan.required_names:
            if not is_required_for(field_name, raw):
                continue
            per_field[field_name].required += 1
            if field_name not in nilai.missing:
                per_field[field_name].filled += 1

    laporan.fields = [per_field[n] for n in laporan.required_names]
    return laporan


def verdict(report: Report) -> str:
    if not report.measured:
        return "BELUM DIUKUR"
    if report.failed_images:
        return "GAGAL DIUKUR"
    return "TERCAPAI" if report.pass_verdict else "BELUM TERCAPAI"


# ------------------------------------------------------------------- laporan


def write_report(report: Report, out_dir: Path) -> tuple[Path, Path]:
    """Tulis laporan teks dan CSV. Kembalikan (teks, csv)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    txt = out_dir / "sc06_report.txt"
    csv_path = out_dir / "sc06_images.csv"

    baris = [
        "SC-06: kelengkapan field yang diekstrak dari gambar",
        "=" * 60,
        "",
        "Target (BRD): tidak ada field wajib yang hilang",
        "",
        f"Gambar diuji           : {report.total_images}",
        f"Gambar berhasil dibaca : {report.measured}",
        f"Gambar gagal dipanggil : {report.failed_images}",
        f"Gambar lengkap         : {report.complete_images}",
        "",
        f"{'Field':<18} {'Terisi':>8} {'Wajib':>7} {'Kelengkapan':>12}",
        "-" * 50,
    ]
    for f in report.fields:
        # Penyebut nol berarti field itu tidak wajib pada transaksi mana pun
        # (mis. kantong_tujuan saat tidak ada transfer). Menampilkannya sebagai
        # 0,0% akan terbaca seperti kegagalan, padahal tidak ada yang dinilai.
        rate = f"{f.rate:>11.1f}%" if f.required else f"{'—':>12}"
        baris.append(f"{f.name:<18} {f.filled:>8} {f.required:>7} {rate}")

    baris += [
        "",
        f"Angka yang dinilai : {report.complete_images} dari {report.measured} "
        "gambar lengkap seluruh field wajibnya  <- dibandingkan dengan target",
        f"Status             : {verdict(report)}",
        "",
        "Field yang tidak terbaca dari gambar (gambar terbanyak lebih dulu)",
        "-" * 60,
    ]

    kurang = [i for i in report.images if i.missing]
    kurang.sort(key=lambda i: (-len(i.missing), i.file))
    if not kurang:
        baris.append("  tidak ada — seluruh field wajib terbaca di semua gambar")
    for i in kurang:
        baris.append(f"  {i.file}")
        baris.append(f"      tidak terbaca: {', '.join(i.missing)}")
        if i.covered:
            baris.append(f"      ditutupi nilai bawaan produksi: {', '.join(i.covered)}")

    gagal = [i for i in report.images if i.error]
    if gagal:
        baris += ["", "Gambar yang gagal dipanggil", "-" * 60]
        for i in gagal:
            baris.append(f"  {i.file}: {i.error}")

    if report.covered_total:
        baris += [
            "",
            "Catatan penilaian",
            "-" * 60,
            f"{report.covered_total} field kosong di balasan model tetapi terisi di",
            "aplikasi karena nilai bawaan produksi (tanggal hari ini, arah 'keluar',",
            "nama berkas, atau kantong bawaan). Field seperti itu tetap dinilai",
            "TIDAK TERBACA di sini: pengguna melihat baris terisi, padahal isinya",
            "bukan hasil membaca gambar.",
        ]

    txt.write_text("\n".join(baris) + "\n", encoding="utf-8")

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "complete", "missing", "covered", "error"])
        for i in report.images:
            w.writerow([i.file, "ya" if i.complete else "tidak",
                        "|".join(i.missing), "|".join(i.covered), i.error])
    return txt, csv_path
