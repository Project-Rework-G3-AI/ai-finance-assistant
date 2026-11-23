"""Tes murni tanya-jawab (qa.py): periode, agregasi, command — tanpa jaringan."""

from datetime import date

from cash_report import qa

# 11 kolom A..K: tanggal, kantong, masuk, keluar, kategori, keterangan, status,
# catatan, ref_id, sumber, link
ROWS = [
    ["2026-11-01", "BRI", "100000", "", "Penjualan Produk", "jual kopi", "verified", "", "tg:a", "", "https://x/a"],
    ["2026-11-02", "BRI", "", "50000", "Listrik PLN", "token listrik", "draft", "", "tg:b", "", ""],
    ["2026-11-03", "BRI", "60000", "", "Transfer Antar Bank", "pindah ke Jago", "verified", "", "tg:c", "", ""],
    ["2026-11-03", "Jago", "", "60000", "Transfer Antar Bank", "pindah dari BRI", "verified", "", "tg:c", "", ""],
    ["2026-10-31", "BRI", "999", "", "Listrik PLN", "bulan lalu", "verified", "", "tg:d", "", ""],
    ["", "", "", "", "", "", "", "", "", "", ""],
    ["2026-11-05", "BRI", "70000", "", "Listrik PLN", "tagihan", "VERIFIED", "", "tg:e", "", ""],
]

AWAL, AKHIR = date(2026, 11, 1), date(2026, 12, 1)


def test_parse_period():
    assert qa.parse_period("2026-11") == (AWAL, AKHIR)
    assert qa.parse_period("Nov", today=date(2026, 11, 23)) == (AWAL, AKHIR)
    assert qa.parse_period("November", today=date(2026, 11, 23)) == (AWAL, AKHIR)
    assert qa.parse_period("Desember", today=date(2026, 11, 23)) == (date(2026, 12, 1), date(2027, 1, 1))
    assert qa.parse_period("2026-13") is None
    assert qa.parse_period("abc") is None


def test_tgl_format_sheets_en_us():
    # Tampilan default Sheets en_US: "6-Jan-26" — tanpa ini /total nihil.
    assert qa._tgl("6-Jan-26") == date(2026, 1, 6)
    assert qa._tgl("24-Jan-26") == date(2026, 1, 24)
    assert qa._tgl("2026-11-05") == date(2026, 11, 5)
    assert qa._tgl("11/20/2026") == date(2026, 11, 20)
    assert qa._tgl("20/11/2026") == date(2026, 11, 20)
    assert qa._tgl("bukan tanggal") is None
    assert qa._tgl("") is None


def test_num_tampilan_dan_mentah():
    # Sel nominal tampil "Rp40,400"; get_values mengembalikan tampilan itu.
    assert qa._num("Rp40,400") == 40400
    assert qa._num("Rp40.400") == 40400
    assert qa._num("40400") == 40400
    assert qa._num("1,234.56") == 1234.56
    assert qa._num("") == 0
    assert qa._num("kosong") == 0


def test_aggregate_verified_draft_terpisah():
    tot = qa.aggregate(ROWS, AWAL, AKHIR)
    assert tot["verified"]["masuk"] == 170000  # 100k + 70k, transfer & Oktober excluded
    assert tot["verified"]["keluar"] == 0
    assert tot["verified"]["n"] == 2
    assert tot["draft"]["keluar"] == 50000
    assert tot["draft"]["n"] == 1
    assert tot["transfer"] == 60000
    assert tot["transfer_n"] == 2


def test_aggregate_arah_tidak_memutus_transfer():
    tot = qa.aggregate(ROWS, AWAL, AKHIR, arah="keluar")
    assert tot["draft"]["keluar"] == 50000
    assert tot["transfer"] == 60000
    tot = qa.aggregate(ROWS, AWAL, AKHIR, arah="masuk")
    assert tot["verified"]["masuk"] == 170000
    assert tot["transfer"] == 60000


def test_aggregate_kategori():
    tot = qa.aggregate(ROWS, AWAL, AKHIR, kategori="Listrik PLN")
    assert tot["verified"]["masuk"] == 70000
    assert tot["draft"]["keluar"] == 50000


def test_rekap_tanpa_transfer():
    items = dict(qa.rekap(ROWS, AWAL, AKHIR))
    assert "Transfer Antar Bank" not in items
    assert items["Listrik PLN"]["dk"] == 50000
    assert items["Penjualan Produk"]["vm"] == 100000


def test_list_rows_limit_dan_status():
    baris = qa.list_rows(ROWS, AWAL, AKHIR, limit=2)
    assert len(baris) == 2
    assert baris[0]["tanggal"] == "2026-11-01"
    assert baris[0]["status"] == "verified"


def test_find_receipt():
    assert qa.find_receipt(ROWS, "tg:a") == "https://x/a"
    assert qa.find_receipt(ROWS, "tg:c") is None  # ada barisnya, link kosong
    assert qa.find_receipt(ROWS, "tg:zzz") is None


def _load(_year: str):
    return ROWS


def test_command_reply():
    out = qa.command_reply("/total Nov", _load)
    assert "Total November 2026" in out
    assert "Rp170,000" in out and "Draft" in out and "Verified" in out
    assert qa.command_reply("/total", _load).startswith("Format:")
    assert qa.command_reply("/total kapan", _load).startswith("Format:")
    assert "Rekap" in qa.command_reply("/rekap Nov", _load)
    assert qa.command_reply("/help", _load) == qa.HELP
    assert qa.command_reply("/mulu", _load) == qa.HELP
    assert qa.command_reply("halo bot", _load) is None


def test_balasan_html_aman_dari_tag_mentah():
    """Telegram parse_mode=HTML menolak '<bulan>' (bug 400 di /help)."""
    import re
    tag_izin = re.compile(r"</?(?:b|i)>")
    for teks in (qa.HELP, qa.FALLBACK, qa._FORMAT_ERROR):
        sisa = tag_izin.sub("", teks)
        assert "<" not in sisa and ">" not in sisa, teks
    assert "&lt;bulan&gt;" in qa.HELP
