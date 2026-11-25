"""SC-05: bukti transaksi berulang tidak menimbulkan pencatatan ganda.

Target BRD: **seluruh duplikat ditolak**.

## Apa yang diukur

Bukan isi, bukan waktu, bukan biaya. Yang diukur: **berapa baris yang tersimpan**
ketika berkas yang sama dikirim lebih dari sekali. Satu kiriman berulang harus
tetap menghasilkan satu baris.

## Kenapa pengukuran ini memakai jalur Telegram yang asli

`handle_update` dari `main.py` dipanggil apa adanya, bukan disalin. Yang diganti
hanya tiga hal di luar aplikasi:

1. **Telegram** diganti tiruan, karena tidak ada bot token di mesin ini.
2. **Google Sheets** diganti worksheet tiruan yang meniru `col_values` dan
   `update`, karena dedup hanya membaca kolom Ref ID lalu menambah baris.
3. **Ekstraksi AI** diganti jawaban tetap, karena SC-05 menguji dedup, bukan
   mutu pembacaan gambar. Memanggil model di sini hanya membakar biaya tanpa
   menambah bukti.

Yang **tidak** diganti: logika dedup, urutan pemeriksaan, dan cara `ref_id`
dibentuk. Itu justru yang dinilai.

## Tiga kasus, dan kenapa harus tiga

| Kasus | Harapan | Alasan |
|---|---|---|
| Kirim ulang berkas yang sama | **ditolak** | inti kriteria |
| Isi sama, `file_id` berbeda | **ditolak** menurut BRD | BRD menyebut pengenalan lewat hash |
| Gambar berbeda | **tetap dicatat** | kendali |

Kasus ketiga bukan pelengkap. Tanpa kendali, dedup yang menolak **semua**
kiriman akan terlihat lulus sempurna padahal merusak aplikasi. Kendali inilah
yang membedakan "dedup benar" dari "dedup terlalu agresif".

Kasus kedua diberi label **temuan**, bukan wajib, karena kode memang tidak
memakai hash. BRD menyebut hash di ruang lingkup dan UC-03, jadi selisihnya
dilaporkan apa adanya, tidak disembunyikan dan tidak dipaksakan lulus.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Kolom TRANSAKSI, A sampai K. Sama dengan yang ditulis `write_cash_report`.
HEADER = ["Tanggal", "Kantong", "Uang Masuk", "Uang Keluar", "Kategori",
          "Keterangan", "Status", "Catatan", "Ref ID", "Sumber File", "Link Bukti"]
KOLOM_REF_ID = 9  # kolom I

# Rekaman transaksi tetap. Isinya tidak penting untuk SC-05; yang penting
# `ref_id`, karena dedup hanya memeriksa itu.
REKAMAN = {
    "tanggal": "2026-01-15",
    "keterangan": "Transfer dari pelanggan",
    "nominal": 195000,
    "arah": "masuk",
    "kategori": "Pendapatan Usaha",
    "bank": "BNI",
    "kantong_tujuan": "",
    "catatan": "",
}


class FakeWorksheet:
    """Worksheet tiruan: hanya yang dipakai `write_cash_report`.

    Meniru perilaku Google Sheets yang relevan: `col_values` memangkas sel kosong
    di ujung, dan `update` menulis pada rentang A:K yang diberikan.
    """

    def __init__(self, title: str = "TRANSAKSI", header: list[str] | None = None,
                 rows: list[list[str]] | None = None):
        self.title = title
        self.grid: list[list[str]] = [list(header or HEADER)]
        for r in rows or []:
            self.grid.append(list(r))

    def col_values(self, n: int) -> list[str]:
        col = [(r[n - 1] if len(r) >= n else "") for r in self.grid]
        while col and not str(col[-1]).strip():
            col.pop()
        return col

    def update(self, values=None, range_name: str = "",
               value_input_option: str = "", **kwargs) -> None:
        m = re.match(r"A(\d+):K(\d+)", range_name or "")
        if not m:
            raise AssertionError(f"rentang tak terduga: {range_name!r}")
        mulai = int(m.group(1))
        for i, baris in enumerate(values or []):
            nomor = mulai + i
            while len(self.grid) < nomor:
                self.grid.append([])
            target = self.grid[nomor - 1]
            for j, v in enumerate(baris):
                while len(target) <= j:
                    target.append("")
                target[j] = v

    # --- pembantu untuk pemeriksaan ---

    @property
    def baris_data(self) -> list[list[str]]:
        return self.grid[1:]

    @property
    def jumlah_baris(self) -> int:
        return len(self.baris_data)

    def ref_ids(self) -> list[str]:
        return [r[KOLOM_REF_ID - 1] for r in self.baris_data
                if len(r) >= KOLOM_REF_ID and str(r[KOLOM_REF_ID - 1]).strip()]


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakeTelegram:
    """Klien HTTP tiruan untuk mengunduh gambar dan mencatat balasan bot."""

    def __init__(self, gambar: bytes):
        self.gambar = gambar
        self.balasan: list[str] = []

    async def get(self, url: str, timeout: int | None = None) -> FakeResponse:
        return FakeResponse(self.gambar)


# Nama fungsi dan variabel modul yang diganti `pasang_tiruan`, dicatat di satu
# tempat supaya pemulihannya tidak bisa ketinggalan.
DIGANTI = ("_find_or_create_folder", "_find_or_create_spreadsheet",
           "_open_spreadsheet", "_drive_ready", "extract", "tg_call")


def pulihkan(main, asli: dict) -> None:
    """Kembalikan modul ke keadaan sebelum `pasang_tiruan`.

    Tanpa ini, tiruan tertinggal di modul dan mencemari test lain yang berjalan
    setelahnya. Gejalanya menyesatkan: test lulus sendiri-sendiri tetapi gagal
    saat seluruh suite dijalankan.
    """
    for nama, nilai in asli.items():
        setattr(main, nama, nilai)


def pasang_tiruan(main, ws: FakeWorksheet, gambar: bytes) -> dict:
    """Arahkan aplikasi ke Sheets tiruan dan matikan Drive serta model.

    Hanya fungsi di luar aplikasi yang diganti. `write_cash_report` dan
    `handle_update` tetap yang asli, karena logika dedup ada di sana.

    Mengembalikan keadaan asli untuk diberikan ke `pulihkan`.
    """
    asli = {nama: getattr(main, nama) for nama in DIGANTI if hasattr(main, nama)}
    asli["CR_FOLDER_ID"] = getattr(main, "CR_FOLDER_ID", None)
    asli["CR_TEMPLATE_ID"] = getattr(main, "CR_TEMPLATE_ID", None)
    asli["CR_DEFAULT_BANK"] = getattr(main, "CR_DEFAULT_BANK", None)

    main.CR_FOLDER_ID = "folder-uji"
    main.CR_TEMPLATE_ID = "template-uji"
    main.CR_DEFAULT_BANK = "BNI"

    main._find_or_create_folder = lambda nama, induk: "folder-uji"
    main._find_or_create_spreadsheet = lambda tahun, folder: {
        "id": "ss-uji", "name": f"Cash Report {tahun}"}

    class _Sheet:
        def worksheet(self, nama: str):
            if nama != ws.title:
                raise AssertionError(f"worksheet tak terduga: {nama}")
            return ws

    main._open_spreadsheet = lambda ss_id: _Sheet()
    main._drive_ready = lambda: False

    async def ekstrak_tetap(client, filename, image_bytes, caption):
        return dict(REKAMAN)

    main.extract = ekstrak_tetap

    async def tg_call_tiruan(client, method, **payload):
        if method != "getFile":
            raise AssertionError(f"tg_call tak terduga: {method}")
        return {"file_path": f"photos/{payload.get('file_id')}.jpg"}

    main.tg_call = tg_call_tiruan
    return asli


@dataclass
class Kiriman:
    """Satu unggahan yang disimulasikan."""

    file_id: str
    gambar: bytes
    caption: str = ""


@dataclass
class Case:
    """Satu skenario pengiriman berulang.

    `expected_rows` adalah jumlah baris yang seharusnya tersimpan. Dibandingkan
    dengan jumlah baris nyata, bukan dengan kata "ditolak", supaya bisa mengukur
    berapa dari berapa yang benar-benar tertolak.
    """

    name: str
    label: str
    requirement: str          # "wajib" | "kendali" | "temuan"
    expected_rows: int
    kiriman: list[Kiriman] = field(default_factory=list)
    baris: int = 0
    balasan_duplikat: int = 0
    error: str = ""

    @property
    def duplikat(self) -> int:
        """Berapa kiriman berulang yang berhasil ditolak."""
        return max(0, len(self.kiriman) - self.baris)

    @property
    def duplikat_harus_ditolak(self) -> int:
        return len(self.kiriman) - self.expected_rows

    @property
    def sesuai_harapan(self) -> bool:
        return self.baris == self.expected_rows


async def jalankan_case(main, case: Case) -> Case:
    """Kirim seluruh berkas pada satu skenario, hitung baris yang tersimpan."""
    ws = FakeWorksheet()
    asli = pasang_tiruan(main, ws, b"")
    try:
        await _kirim_semua(main, case, ws)
    finally:
        pulihkan(main, asli)
    return case


async def _kirim_semua(main, case: Case, ws: FakeWorksheet) -> None:
    for i, kirim in enumerate(case.kiriman, 1):
        klien = FakeTelegram(kirim.gambar)
        main.tg_send = _perekam_balasan(klien)
        upd = {
            "message": {
                "chat": {"id": 111},
                "photo": [{"file_id": kirim.file_id}],
                "date": 1700000000 + i,
                "caption": kirim.caption,
            }
        }
        await main.handle_update(klien, upd)
        case.balasan_duplikat += sum(
            1 for b in klien.balasan if "Sudah pernah dicatat" in b)
    case.baris = ws.jumlah_baris


def _perekam_balasan(klien: FakeTelegram):
    async def tg_send(client, chat_id, text):
        klien.balasan.append(text)
    return tg_send


def _gambar_uji(n: int) -> list[bytes]:
    """Lima gambar berbeda isinya, dibuat di dalam test.

    Isinya tidak penting; yang penting berbeda satu sama lain supaya bisa
    dibedakan bila tercatat sebagai baris terpisah.
    """
    return [b"\xff\xd8\xff\xe0" + f"bukti-{i}".encode() * 10 + b"\xff\xd9"
            for i in range(n)]


def bangun_cases(jumlah_gambar: int = 5) -> list[Case]:
    """Tiga skenario, masing-masing memakai beberapa gambar.

    Memakai beberapa gambar sekaligus supaya angkanya punya penyebut yang berarti:
    "lima dari lima duplikat ditolak" jauh lebih kuat daripada "satu dari satu".
    """
    gambar = _gambar_uji(jumlah_gambar)

    # 1. Berkas yang sama dikirim ulang: file_id sama, isi sama.
    sama = []
    for i, g in enumerate(gambar):
        sama += [Kiriman(f"AgACAgUAAxkBAAI{i}", g),
                 Kiriman(f"AgACAgUAAxkBAAI{i}", g)]

    # 2. Isi sama tetapi file_id berbeda, meniru unggah ulang dari galeri.
    beda_id = []
    for i, g in enumerate(gambar):
        beda_id += [Kiriman(f"AgACAgUAAxkBAAI{i}", g),
                    Kiriman(f"AgACAgUAAxkBBBB{i}", g)]

    # 3. Kendali: gambar berbeda, masing-masing sekali. Semua harus tercatat.
    kendali = [Kiriman(f"AgACAgUAAxkBCCC{i}", g) for i, g in enumerate(gambar)]

    return [
        Case(
            name="kirim_ulang_berkas_sama",
            label="Kirim ulang berkas yang sama",
            requirement="wajib",
            expected_rows=len(gambar),
            kiriman=sama,
        ),
        Case(
            name="isi_sama_file_id_baru",
            label="Isi sama, file_id berbeda",
            requirement="temuan",
            expected_rows=len(gambar),
            kiriman=beda_id,
        ),
        Case(
            name="gambar_berbeda",
            label="Gambar berbeda (kendali)",
            requirement="kendali",
            expected_rows=len(gambar),
            kiriman=kendali,
        ),
    ]


async def ukur(main, jumlah_gambar: int = 5) -> list[Case]:
    cases = bangun_cases(jumlah_gambar)
    for c in cases:
        try:
            await jalankan_case(main, c)
        except Exception as e:  # noqa: BLE001
            c.error = f"{type(e).__name__}: {e}"
    return cases


def compute(cases: list[Case]) -> dict:
    """Ringkas hasil.

    Status hanya ditentukan kasus **wajib** dan **kendali**. Kasus temuan
    dilaporkan terpisah: ia menunjukkan selisih terhadap BRD, tetapi kode yang
    ada memang tidak dirancang untuk itu, jadi tidak dipakai menghukum.

    Yang dinilai adalah **berapa duplikat yang ditolak**, bukan sekadar berapa
    skenario yang "sesuai". Dengan lima gambar, angkanya jadi "lima dari lima",
    bukan "satu dari satu".
    """
    wajib = [c for c in cases if c.requirement == "wajib"]
    kendali = [c for c in cases if c.requirement == "kendali"]
    temuan = [c for c in cases if c.requirement == "temuan"]

    wajib_harus = sum(c.duplikat_harus_ditolak for c in wajib)
    wajib_benar = sum(c.duplikat for c in wajib)
    kendali_lulus = sum(1 for c in kendali if c.sesuai_harapan)

    hasil = {
        "cases": [
            {"name": c.name, "label": c.label, "requirement": c.requirement,
             "uploads": len(c.kiriman), "rows": c.baris,
             "expected_rows": c.expected_rows,
             "duplicates_rejected": c.duplikat,
             "duplicates_expected": c.duplikat_harus_ditolak,
             "dup_replies": c.balasan_duplikat,
             "as_expected": c.sesuai_harapan, "error": c.error}
            for c in cases
        ],
        "required_rejected": wajib_benar,
        "required_duplicates": wajib_harus,
        "control_total": len(kendali),
        "control_passed": kendali_lulus,
        "findings_rejected": sum(c.duplikat for c in temuan),
        "findings_duplicates": sum(c.duplikat_harus_ditolak for c in temuan),
        "measured": len(cases),
    }
    # Lulus hanya bila seluruh duplikat wajib ditolak DAN kendali tidak ikut
    # tertolak. Tanpa syarat kedua, dedup yang menolak segalanya akan lulus.
    hasil["pass"] = bool(wajib) and bool(wajib_harus) \
        and wajib_benar == wajib_harus \
        and kendali_lulus == len(kendali)
    return hasil


def verdict(c: dict) -> str:
    if not c.get("measured"):
        return "BELUM DIUKUR"
    return "TERCAPAI" if c.get("pass") else "BELUM TERCAPAI"


def report(c: dict, source: str = "") -> str:
    baris = ["SC-05 — Bukti transaksi berulang tidak mencatat ganda", "=" * 60]
    if source:
        baris.append(source)
    baris.append("")

    if not c.get("measured"):
        return "\n".join(baris + [
            f"Status             : {verdict(c)}",
            "",
            "Belum ada hasil. Jalankan:",
            "",
            "  python3 tests/_sc05_run.py",
        ])

    baris += [
        "Target             : seluruh duplikat ditolak",
        f"Angka yang dinilai : {c['required_rejected']} dari "
        f"{c['required_duplicates']} berkas duplikat ditolak  "
        "<- dibandingkan dengan target",
        f"Status             : {verdict(c)}",
        "",
        "Rincian skenario",
        "-" * 60,
    ]
    for k in c["cases"]:
        tanda = "sesuai" if k["as_expected"] else "TIDAK sesuai"
        baris.append(f"  {k['label']}")
        baris.append(f"    {k['uploads']} kiriman -> {k['rows']} baris tersimpan "
                     f"(harapan {k['expected_rows']}) — {tanda}")
        if k["duplicates_expected"]:
            baris.append(f"    duplikat ditolak: {k['duplicates_rejected']} "
                         f"dari {k['duplicates_expected']}")
        if k["dup_replies"]:
            baris.append(f"    balasan 'sudah pernah dicatat': {k['dup_replies']}")
        if k["error"]:
            baris.append(f"    GAGAL DIUKUR: {k['error']}")
    baris.append("")

    if c["control_total"]:
        baris += [
            "Kendali",
            "-" * 60,
            f"  gambar berbeda tetap dicatat: {c['control_passed']} dari "
            f"{c['control_total']} skenario sesuai",
            "  Tanpa kendali, dedup yang menolak semua kiriman akan tampak lulus.",
            "",
        ]

    if c["findings_duplicates"]:
        baris += [
            "Temuan terhadap BRD",
            "-" * 60,
            f"  isi sama dengan file_id berbeda: {c['findings_rejected']} dari "
            f"{c['findings_duplicates']} ditolak",
            "  BRD menyebut pengenalan duplikat lewat hash berkas, sedangkan kode",
            "  memakai identitas berkas dari Telegram. Selisih ini dilaporkan,",
            "  tidak dipakai menghukum karena kode memang tidak memakai hash.",
            "",
        ]
    return "\n".join(baris)


def write_report(c: dict, out: Path, source: str = "") -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "sc05_report.txt").write_text(report(c, source), encoding="utf-8")
    (out / "sc05_metrics.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
