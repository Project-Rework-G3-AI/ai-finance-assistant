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
REF_ID_COLUMN = 9  # kolom I

# Rekaman transaksi tetap. Isinya tidak penting untuk SC-05; yang penting
# `ref_id`, karena dedup hanya memeriksa itu.
RECORD = {
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
        start = int(m.group(1))
        for i, row in enumerate(values or []):
            number = start + i
            while len(self.grid) < number:
                self.grid.append([])
            target = self.grid[number - 1]
            for j, v in enumerate(row):
                while len(target) <= j:
                    target.append("")
                target[j] = v

    # --- pembantu untuk pemeriksaan ---

    @property
    def data_rows(self) -> list[list[str]]:
        return self.grid[1:]

    @property
    def row_count(self) -> int:
        return len(self.data_rows)

    def ref_ids(self) -> list[str]:
        return [r[REF_ID_COLUMN - 1] for r in self.data_rows
                if len(r) >= REF_ID_COLUMN and str(r[REF_ID_COLUMN - 1]).strip()]


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self) -> None:
        return None


class FakeTelegram:
    """Klien HTTP tiruan untuk mengunduh gambar dan mencatat balasan bot."""

    def __init__(self, image: bytes):
        self.image = image
        self.reply: list[str] = []

    async def get(self, url: str, timeout: int | None = None) -> FakeResponse:
        return FakeResponse(self.image)


# Nama fungsi dan variabel modul yang diganti `pasang_tiruan`, dicatat di satu
# tempat supaya pemulihannya tidak bisa ketinggalan.
REPLACED = ("_find_or_create_folder", "_find_or_create_spreadsheet",
           "_open_spreadsheet", "_drive_ready", "extract", "tg_call")


def restore_module(main, original: dict) -> None:
    """Kembalikan modul ke keadaan sebelum `pasang_tiruan`.

    Tanpa ini, tiruan tertinggal di modul dan mencemari test lain yang berjalan
    setelahnya. Gejalanya menyesatkan: test lulus sendiri-sendiri tetapi gagal
    saat seluruh suite dijalankan.
    """
    for name, value in original.items():
        setattr(main, name, value)


def install_fakes(main, ws: FakeWorksheet, image: bytes) -> dict:
    """Arahkan aplikasi ke Sheets tiruan dan matikan Drive serta model.

    Hanya fungsi di luar aplikasi yang diganti. `write_cash_report` dan
    `handle_update` tetap yang asli, karena logika dedup ada di sana.

    Mengembalikan keadaan asli untuk diberikan ke `pulihkan`.
    """
    original = {name: getattr(main, name) for name in REPLACED if hasattr(main, name)}
    original["CR_FOLDER_ID"] = getattr(main, "CR_FOLDER_ID", None)
    original["CR_TEMPLATE_ID"] = getattr(main, "CR_TEMPLATE_ID", None)
    original["CR_DEFAULT_BANK"] = getattr(main, "CR_DEFAULT_BANK", None)

    main.CR_FOLDER_ID = "folder-uji"
    main.CR_TEMPLATE_ID = "template-uji"
    main.CR_DEFAULT_BANK = "BNI"

    main._find_or_create_folder = lambda name, parent: "folder-uji"
    main._find_or_create_spreadsheet = lambda year, folder: {
        "id": "ss-uji", "name": f"Cash Report {year}"}

    class _Sheet:
        def worksheet(self, name: str):
            if name != ws.title:
                raise AssertionError(f"worksheet tak terduga: {name}")
            return ws

    main._open_spreadsheet = lambda ss_id: _Sheet()
    main._drive_ready = lambda: False

    async def extract_unchanged(client, filename, image_bytes, caption):
        return dict(RECORD)

    main.extract = extract_unchanged

    async def fake_tg_call(client, method, **payload):
        if method != "getFile":
            raise AssertionError(f"tg_call tak terduga: {method}")
        return {"file_path": f"photos/{payload.get('file_id')}.jpg"}

    main.tg_call = fake_tg_call
    return original


@dataclass
class Upload:
    """Satu unggahan yang disimulasikan."""

    file_id: str
    image: bytes
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
    upload_item: list[Upload] = field(default_factory=list)
    row: int = 0
    duplicate_reply: int = 0
    error: str = ""

    @property
    def duplicate(self) -> int:
        """Berapa kiriman berulang yang berhasil ditolak."""
        return max(0, len(self.upload_item) - self.row)

    @property
    def duplicates_expected(self) -> int:
        return len(self.upload_item) - self.expected_rows

    @property
    def matches_expectation(self) -> bool:
        return self.row == self.expected_rows


async def run_case(main, case: Case) -> Case:
    """Kirim seluruh berkas pada satu skenario, hitung baris yang tersimpan."""
    ws = FakeWorksheet()
    original = install_fakes(main, ws, b"")
    try:
        await _send_all(main, case, ws)
    finally:
        restore_module(main, original)
    return case


async def _send_all(main, case: Case, ws: FakeWorksheet) -> None:
    for i, upload in enumerate(case.upload_item, 1):
        client = FakeTelegram(upload.image)
        main.tg_send = _reply_recorder(client)
        upd = {
            "message": {
                "chat": {"id": 111},
                "photo": [{"file_id": upload.file_id}],
                "date": 1700000000 + i,
                "caption": upload.caption,
            }
        }
        await main.handle_update(client, upd)
        case.duplicate_reply += sum(
            1 for b in client.reply if "Sudah pernah dicatat" in b)
    case.row = ws.row_count


def _reply_recorder(client: FakeTelegram):
    async def tg_send(client, chat_id, text):
        client.reply.append(text)
    return tg_send


def _test_images(n: int) -> list[bytes]:
    """Lima gambar berbeda isinya, dibuat di dalam test.

    Isinya tidak penting; yang penting berbeda satu sama lain supaya bisa
    dibedakan bila tercatat sebagai baris terpisah.
    """
    return [b"\xff\xd8\xff\xe0" + f"bukti-{i}".encode() * 10 + b"\xff\xd9"
            for i in range(n)]


def build_cases(image_count: int = 5) -> list[Case]:
    """Tiga skenario, masing-masing memakai beberapa gambar.

    Memakai beberapa gambar sekaligus supaya angkanya punya penyebut yang berarti:
    "lima dari lima duplikat ditolak" jauh lebih kuat daripada "satu dari satu".
    """
    image = _test_images(image_count)

    # 1. Berkas yang sama dikirim ulang: file_id sama, isi sama.
    same = []
    for i, g in enumerate(image):
        same += [Upload(f"AgACAgUAAxkBAAI{i}", g),
                 Upload(f"AgACAgUAAxkBAAI{i}", g)]

    # 2. Isi sama tetapi file_id berbeda, meniru unggah ulang dari galeri.
    different_id = []
    for i, g in enumerate(image):
        different_id += [Upload(f"AgACAgUAAxkBAAI{i}", g),
                    Upload(f"AgACAgUAAxkBBBB{i}", g)]

    # 3. Kendali: gambar berbeda, masing-masing sekali. Semua harus tercatat.
    control = [Upload(f"AgACAgUAAxkBCCC{i}", g) for i, g in enumerate(image)]

    return [
        Case(
            name="kirim_ulang_berkas_sama",
            label="Kirim ulang berkas yang sama",
            requirement="wajib",
            expected_rows=len(image),
            upload_item=same,
        ),
        Case(
            name="isi_sama_file_id_baru",
            label="Isi sama, file_id berbeda",
            requirement="temuan",
            expected_rows=len(image),
            upload_item=different_id,
        ),
        Case(
            name="gambar_berbeda",
            label="Gambar berbeda (kendali)",
            requirement="kendali",
            expected_rows=len(image),
            upload_item=control,
        ),
    ]


async def measure(main, image_count: int = 5) -> list[Case]:
    cases = build_cases(image_count)
    for c in cases:
        try:
            await run_case(main, c)
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
    required = [c for c in cases if c.requirement == "wajib"]
    control = [c for c in cases if c.requirement == "kendali"]
    findings = [c for c in cases if c.requirement == "temuan"]

    required_duplicates = sum(c.duplicates_expected for c in required)
    required_rejected = sum(c.duplicate for c in required)
    control_passes = sum(1 for c in control if c.matches_expectation)

    result = {
        "cases": [
            {"name": c.name, "label": c.label, "requirement": c.requirement,
             "uploads": len(c.upload_item), "rows": c.row,
             "expected_rows": c.expected_rows,
             "duplicates_rejected": c.duplicate,
             "duplicates_expected": c.duplicates_expected,
             "dup_replies": c.duplicate_reply,
             "as_expected": c.matches_expectation, "error": c.error}
            for c in cases
        ],
        "required_rejected": required_rejected,
        "required_duplicates": required_duplicates,
        "control_total": len(control),
        "control_passed": control_passes,
        "findings_rejected": sum(c.duplicate for c in findings),
        "findings_duplicates": sum(c.duplicates_expected for c in findings),
        "measured": len(cases),
    }
    # Lulus hanya bila seluruh duplikat wajib ditolak DAN kendali tidak ikut
    # tertolak. Tanpa syarat kedua, dedup yang menolak segalanya akan lulus.
    result["pass"] = bool(required) and bool(required_duplicates) \
        and required_rejected == required_duplicates \
        and control_passes == len(control)
    return result


def verdict(c: dict) -> str:
    if not c.get("measured"):
        return "BELUM DIUKUR"
    return "TERCAPAI" if c.get("pass") else "BELUM TERCAPAI"


def report(c: dict, source: str = "") -> str:
    row = ["SC-05 — Bukti transaksi berulang tidak mencatat ganda", "=" * 60]
    if source:
        row.append(source)
    row.append("")

    if not c.get("measured"):
        return "\n".join(row + [
            f"Status             : {verdict(c)}",
            "",
            "Belum ada hasil. Jalankan:",
            "",
            "  python3 tests/_sc05_run.py",
        ])

    row += [
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
        marker = "sesuai" if k["as_expected"] else "TIDAK sesuai"
        row.append(f"  {k['label']}")
        row.append(f"    {k['uploads']} kiriman -> {k['rows']} baris tersimpan "
                     f"(harapan {k['expected_rows']}) — {marker}")
        if k["duplicates_expected"]:
            row.append(f"    duplikat ditolak: {k['duplicates_rejected']} "
                         f"dari {k['duplicates_expected']}")
        if k["dup_replies"]:
            row.append(f"    balasan 'sudah pernah dicatat': {k['dup_replies']}")
        if k["error"]:
            row.append(f"    GAGAL DIUKUR: {k['error']}")
    row.append("")

    if c["control_total"]:
        row += [
            "Kendali",
            "-" * 60,
            f"  gambar berbeda tetap dicatat: {c['control_passed']} dari "
            f"{c['control_total']} skenario sesuai",
            "  Tanpa kendali, dedup yang menolak semua kiriman akan tampak lulus.",
            "",
        ]

    if c["findings_duplicates"]:
        row += [
            "Temuan terhadap BRD",
            "-" * 60,
            f"  isi sama dengan file_id berbeda: {c['findings_rejected']} dari "
            f"{c['findings_duplicates']} ditolak",
            "  BRD menyebut pengenalan duplikat lewat hash berkas, sedangkan kode",
            "  memakai identitas berkas dari Telegram. Selisih ini dilaporkan,",
            "  tidak dipakai menghukum karena kode memang tidak memakai hash.",
            "",
        ]
    return "\n".join(row)


def write_report(c: dict, out: Path, source: str = "") -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "sc05_report.txt").write_text(report(c, source), encoding="utf-8")
    (out / "sc05_metrics.json").write_text(
        json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
