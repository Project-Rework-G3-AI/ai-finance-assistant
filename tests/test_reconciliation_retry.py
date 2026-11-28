"""Test perilaku percobaan ulang pada pembacaan halaman mutasi.

Yang dijaga: satu halaman yang dijawab kosong oleh model tidak boleh
menghentikan seluruh mutasi. Sebelum perbaikan, balasan kosong langsung menjadi
`ValueError` dan seluruh proses rekonsiliasi berhenti; dari empat kali
pengukuran SC-07, dua berhenti karena itu.

Model tidak dipanggil di sini. Yang diuji adalah lapisan yang memutuskan kapan
permintaan diulang, bukan mutu jawaban model.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import reconciliation.vision_extractor as extractor  # noqa: E402


HALAMAN_VALID = {
    "bank": "BRI",
    "account_number": "306601000009566",
    "period_start": "2026-01-01",
    "period_end": "2026-01-31",
    "opening_balance": 214531779.0,
    "closing_balance": 192643952.0,
    "total_debit": 22066136.0,
    "total_credit": 178309.0,
    "page_type": "transactions",
    "transactions": [],
}


def _pasang_balasan(monkeypatch, daftar_balasan):
    """Ganti permintaan jaringan dengan balasan berurutan yang sudah disiapkan."""
    dipanggil = []

    async def palsu(**kwargs):
        dipanggil.append(kwargs.get("page_number"))
        return daftar_balasan[len(dipanggil) - 1]

    monkeypatch.setattr(extractor, "_request_statement_page", palsu)
    monkeypatch.setattr(extractor, "EMPTY_RESPONSE_DELAY", 0)
    return dipanggil


def _jalankan():
    return asyncio.run(
        extractor.extract_statement_page(
            client=None,
            image_bytes=b"",
            page_number=3,
            ai_key="k",
            ai_base="http://x",
            ai_model="m",
        )
    )


def test_empty_reply_is_retried_and_succeeds(monkeypatch):
    """Balasan kosong diikuti balasan benar harus berakhir berhasil."""
    dipanggil = _pasang_balasan(monkeypatch, [None, "", json.dumps(HALAMAN_VALID)])

    hasil = _jalankan()

    assert hasil["account_number"] == "306601000009566"
    assert hasil["page_number"] == 3
    assert len(dipanggil) == 3, "halaman harus diminta ulang setelah balasan kosong"


def test_invalid_json_is_retried(monkeypatch):
    """Balasan yang bukan JSON juga tidak terpakai, jadi harus diulang."""
    _pasang_balasan(monkeypatch, ["bukan json", json.dumps(HALAMAN_VALID)])

    hasil = _jalankan()

    assert hasil["page_number"] == 3


def test_retry_limit_is_small_and_bounded():
    """Retries must stay few: every attempt costs time and money.

    A PDF has up to seven pages. If a blank reply were retried many times, one
    slow statement could hold the bot for minutes. The limit is pinned to a
    small number so raising it is a deliberate decision.
    """
    assert 1 < extractor.EMPTY_RESPONSE_ATTEMPTS <= 3, (
        "retry limit must stay small; each attempt is a paid model call"
    )
    assert extractor.EMPTY_RESPONSE_DELAY <= 2, "backoff must stay short"


def test_retry_gives_up_after_the_limit(monkeypatch):
    """Bila semua percobaan kosong, galatnya harus jelas dan menyebut halaman."""
    batas = extractor.EMPTY_RESPONSE_ATTEMPTS
    dipanggil = _pasang_balasan(monkeypatch, [None] * batas)

    with pytest.raises(extractor.EmptyResponseError) as excinfo:
        _jalankan()

    assert excinfo.value.page_number == 3
    assert excinfo.value.reason == "empty"
    assert len(dipanggil) == batas, (
        "jumlah permintaan harus sama dengan batas percobaan, tidak lebih"
    )
    assert len(dipanggil) <= 3, "an unbounded retry would hang the bot"


def test_http_error_is_not_retried_here(monkeypatch):
    """Galat HTTP tetap urusan `post_with_retry`, bukan lapisan ini.

    Kalau lapisan ini ikut mengulang galat HTTP, satu permintaan bisa diulang
    berkali-kali oleh dua lapisan sekaligus. Karena itu jumlah panggilan dihitung.
    """
    import httpx

    dipanggil = []

    async def gagal(**kwargs):
        dipanggil.append(1)
        raise httpx.HTTPStatusError(
            "500", request=httpx.Request("POST", "http://x"), response=httpx.Response(500)
        )

    monkeypatch.setattr(extractor, "_request_statement_page", gagal)
    monkeypatch.setattr(extractor, "EMPTY_RESPONSE_DELAY", 0)

    with pytest.raises(httpx.HTTPStatusError):
        _jalankan()

    assert len(dipanggil) == 1, (
        "an HTTP error must be raised at once; retrying it here would double "
        "the retries already done by post_with_retry"
    )


def test_empty_reply_no_longer_aborts_without_retry():
    """Penjaga terhadap kemunduran: lapisan retry harus ada.

    Test ini merah bila `extract_statement_page` kembali menjadi satu panggilan
    tanpa percobaan ulang.
    """
    import inspect

    sumber = inspect.getsource(extractor.extract_statement_page)
    assert "_request_statement_page" in sumber
    assert "EMPTY_RESPONSE_ATTEMPTS" in sumber
    assert extractor.EMPTY_RESPONSE_ATTEMPTS >= 2
