"""Aturan SC-05: duplikat tidak boleh menghasilkan baris ganda.

Yang dikunci di sini ada dua lapis.

Pertama, **logika penilaian**: kapan sebuah pengukuran disebut lulus. Termasuk
syarat yang mudah terlupa, yaitu kendali. Tanpa kendali, dedup yang menolak
semua kiriman akan tampak lulus sempurna.

Kedua, **harness benar-benar bisa merah**: bila pemeriksaan duplikat dimatikan,
hasilnya harus BELUM TERCAPAI. Tanpa bukti ini, angka "lima dari lima" hanya
klaim yang tidak bisa dibedakan dari harness yang selalu hijau.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sc05_dedupe as sc05  # noqa: E402


# ------------------------------------------------------- penilaian

def case(requirement="wajib", uploads=2, rows=1, expected=1):
    return sc05.Case(
        name="uji", label="uji", requirement=requirement,
        expected_rows=expected,
        upload_item=[sc05.Upload(f"id{i}", b"x") for i in range(uploads)],
        row=rows,
    )


def test_all_required_duplicates_rejected_passes():
    c = sc05.compute([case("wajib", uploads=2, rows=1, expected=1),
                      case("kendali", uploads=1, rows=1, expected=1)])
    assert c["required_rejected"] == 1
    assert c["required_duplicates"] == 1
    assert c["pass"] is True
    assert sc05.verdict(c) == "TERCAPAI"


def test_one_duplicate_escaping_fails():
    """Satu saja yang lolos berarti tidak "seluruhnya" ditolak."""
    c = sc05.compute([case("wajib", uploads=2, rows=2, expected=1),
                      case("kendali", uploads=1, rows=1, expected=1)])
    assert c["required_rejected"] == 0
    assert c["pass"] is False
    assert sc05.verdict(c) == "BELUM TERCAPAI"


def test_five_images_give_a_meaningful_denominator():
    """Lima gambar harus menghasilkan penyebut lima, bukan satu."""
    cases = sc05.build_cases(5)
    required = next(c for c in cases if c.requirement == "wajib")
    assert len(required.upload_item) == 10          # lima gambar, masing-masing dua kali
    assert required.expected_rows == 5
    assert required.duplicates_expected == 5


def test_control_failure_fails_the_criterion():
    """Dedup yang menolak semua kiriman tidak boleh disebut lulus.

    Ini syarat yang mudah terlupa: kalau hanya kasus wajib yang diperiksa,
    aplikasi yang menolak segalanya akan lulus 100%.
    """
    c = sc05.compute([case("wajib", uploads=2, rows=1, expected=1),
                      case("kendali", uploads=1, rows=0, expected=1)])
    assert c["pass"] is False


def test_no_control_means_no_control_credit():
    c = sc05.compute([case("wajib", uploads=2, rows=1, expected=1)])
    assert c["control_total"] == 0
    assert c["control_passed"] == 0


def test_findings_do_not_decide_the_verdict():
    """Temuan terhadap BRD dilaporkan, tetapi tidak dipakai menghukum.

    Kode memang tidak memakai hash, jadi kegagalan kasus ini adalah selisih
    terhadap dokumen, bukan kegagalan yang bisa diperbaiki tanpa mengubah
    produksi.
    """
    passes = sc05.compute([
        case("wajib", uploads=2, rows=1, expected=1),
        case("kendali", uploads=1, rows=1, expected=1),
        case("temuan", uploads=2, rows=2, expected=1),
    ])
    assert passes["findings_rejected"] == 0
    assert passes["findings_duplicates"] == 1
    assert passes["pass"] is True


def test_nothing_measured_never_passes():
    c = sc05.compute([])
    assert c["measured"] == 0
    assert c["pass"] is False
    assert sc05.verdict(c) == "BELUM DIUKUR"


def test_duplicate_count_is_uploads_minus_rows():
    c = case("wajib", uploads=4, rows=2, expected=1)
    assert c.duplicate == 2
    assert c.duplicates_expected == 3
    assert c.matches_expectation is False


# ------------------------------------------------------- laporan

def test_report_names_the_judged_number_before_the_status():
    c = sc05.compute([case("wajib", uploads=2, rows=1, expected=1),
                      case("kendali", uploads=1, rows=1, expected=1)])
    text = sc05.report(c)
    assert text.index("Angka yang dinilai") < text.index("Status")
    assert "1 dari 1" in text


def test_report_states_the_target_in_words():
    c = sc05.compute([case("wajib", uploads=2, rows=1, expected=1),
                      case("kendali", uploads=1, rows=1, expected=1)])
    assert "seluruh duplikat ditolak" in sc05.report(c)


def test_report_shows_every_case_with_rows_and_uploads():
    c = sc05.compute([case("wajib", uploads=2, rows=1, expected=1)])
    text = sc05.report(c)
    assert "2 kiriman" in text
    assert "1 baris tersimpan" in text


def test_report_explains_the_control():
    c = sc05.compute([case("wajib", uploads=2, rows=1, expected=1),
                      case("kendali", uploads=1, rows=1, expected=1)])
    assert "Kendali" in sc05.report(c)


def test_report_says_not_measured_without_cases():
    text = sc05.report(sc05.compute([]))
    assert "BELUM DIUKUR" in text
    assert "_sc05_run.py" in text


# ------------------------------------------------------- harness bisa merah

def disable_dedup(monkeypatch):
    """Matikan pemeriksaan duplikat saja, tanpa merusak pencarian baris.

    `col_values` dipakai untuk dua hal: mencari baris kosong (kolom 1) dan
    memeriksa Ref ID (kolom 9). Mengosongkan semuanya akan membuat penulisan
    menimpa header, sehingga yang terukur bukan lagi dedup. Karena itu hanya
    kolom 9 yang dikosongkan.
    """
    original = sc05.FakeWorksheet.col_values

    def only_ref_id(self, n):
        if n == sc05.REF_ID_COLUMN:
            return []
        return original(self, n)

    monkeypatch.setattr(sc05.FakeWorksheet, "col_values", only_ref_id)


@pytest.fixture
def app_with_sheet():
    """Siapkan aplikasi dengan Sheets tiruan; kembalikan (main, ws)."""
    import main as app

    ws = sc05.FakeWorksheet()
    sc05.install_fakes(app, ws, b"")
    return app, ws


def test_harness_passes_when_dedupe_works(app_with_sheet):
    """Kondisi normal: duplikat ditolak."""
    app, ws = app_with_sheet
    cases = asyncio.run(sc05.measure(app, 3))
    result = sc05.compute(cases)
    required = next(c for c in cases if c.requirement == "wajib")
    assert required.row == 3          # tiga gambar, masing-masing dua kali
    assert result["required_rejected"] == 3
    assert result["pass"] is True


def test_harness_goes_red_when_dedupe_is_disabled(app_with_sheet, monkeypatch):
    """Inti pembuktian: matikan pemeriksaan duplikat, hasil harus gagal.

    Kalau test ini lulus padahal dedup dimatikan, harness-nya tidak mengukur
    apa pun dan angka "lima dari lima" tidak bisa dipercaya.
    """
    app, _ = app_with_sheet

    # Tiru worksheet yang tidak pernah melaporkan Ref ID apa pun, sehingga
    # pemeriksaan duplikat di `write_cash_report` tidak pernah menemukan apa pun.
    disable_dedup(monkeypatch)

    cases = asyncio.run(sc05.measure(app, 3))
    result = sc05.compute(cases)

    required = next(c for c in cases if c.requirement == "wajib")
    assert required.row == 6          # semua kiriman tercatat
    assert result["required_rejected"] == 0
    assert result["pass"] is False
    assert sc05.verdict(result) == "BELUM TERCAPAI"


def test_control_still_passes_when_dedupe_is_disabled(app_with_sheet, monkeypatch):
    """Saat dedup mati, kendali tetap benar.

    Ini memperlihatkan bahwa yang gagal memang dedup-nya, bukan seluruh harness.
    """
    app, _ = app_with_sheet
    disable_dedup(monkeypatch)

    cases = asyncio.run(sc05.measure(app, 3))
    control = next(c for c in cases if c.requirement == "kendali")
    assert control.matches_expectation is True


def test_duplicate_reply_is_sent_to_the_user(app_with_sheet):
    """Pengguna harus diberi tahu, bukan hanya diabaikan diam-diam."""
    app, ws = app_with_sheet
    cases = asyncio.run(sc05.measure(app, 2))
    required = next(c for c in cases if c.requirement == "wajib")
    assert required.duplicate_reply == 2   # dua gambar, satu balasan masing-masing


def test_only_one_row_per_image_is_stored(app_with_sheet):
    """Bukan hanya jumlah baris: Ref ID tidak boleh muncul dua kali."""
    app, ws = app_with_sheet
    sc05.install_fakes(app, ws, b"")
    client = sc05.FakeTelegram(b"x")
    app.tg_send = sc05._reply_recorder(client)
    upd = {"message": {"chat": {"id": 1}, "photo": [{"file_id": "idA"}],
                       "date": 1700000000, "caption": ""}}
    asyncio.run(app.handle_update(client, upd))
    asyncio.run(app.handle_update(client, upd))

    ref = ws.ref_ids()
    assert len(ref) == 1
    assert ref[0] == "tg:idA"
