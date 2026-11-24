"""Tes murni reconciliation: matcher, normalizer, validator, antrean datetime."""

import json
from datetime import date, datetime

import pytest

from cash_report import qa
from reconciliation.matcher import make_match_key, reconcile_transactions, summarize_reconciliation
from reconciliation.normalizer import (
    normalize_amount,
    normalize_bank_transaction,
    normalize_date,
)
from reconciliation.statement_validator import validate_statement


def _bank(date_, pocket, debit=0, credit=0):
    return {"date": date_, "pocket": pocket, "debit": debit, "credit": credit}


def _sheet(date_, pocket, debit=0, credit=0):
    return {"date": date_, "pocket": pocket, "debit": debit, "credit": credit,
            "keterangan": "", "kategori": "", "catatan": "", "ref_id": "",
            "sumber_file": "", "link_bukti": "", "row_number": 2}


def test_make_match_key_casefold_pocket():
    # sheet menulis "JAGO", mapping menulis "Jago" — harus kunci yang sama
    assert make_match_key(_bank("2026-01-06", "Jago", credit=200000)) == \
        make_match_key(_sheet("2026-01-06", "JAGO", credit=200000))


def test_reconcile_kasus_dasar():
    bank = [
        _bank("2026-01-06", "BRI", credit=100000),     # matched
        _bank("2026-01-07", "BRI", debit=50000),       # bank_only
    ]
    sheet = [
        _sheet("2026-01-06", "BRI", credit=100000),
        _sheet("2026-01-08", "BRI", debit=20000),      # sheet_only
        _sheet("2025-12-31", "BRI", debit=1),          # di luar periode -> tak ikut
    ]
    hasil = reconcile_transactions(bank, sheet, "2026-01-01", "2026-01-31")
    status = sorted(r["status"] for r in hasil)
    assert status == ["bank_only", "matched", "sheet_only"]
    ringkas = summarize_reconciliation(hasil)
    assert ringkas == {"total": 3, "matched": 1, "bank_only": 1,
                       "sheet_only": 1, "needs_review": 0}


def test_reconcile_kunci_duplikat_needs_review():
    bank = [
        _bank("2026-01-06", "BRI", credit=75000),
        _bank("2026-01-06", "BRI", credit=75000),
    ]
    sheet = [_sheet("2026-01-06", "BRI", credit=75000)]
    hasil = reconcile_transactions(bank, sheet, "2026-01-01", "2026-01-31")
    assert [r["status"] for r in hasil] == ["needs_review", "needs_review"]
    assert hasil[0]["candidate_sheet_transactions"]


def test_normalize_amount():
    assert normalize_amount("Rp40.400") == 40400
    assert normalize_amount("1.500.000") == 1500000
    assert normalize_amount("Rp40,400") == 40400
    assert normalize_amount(40400) == 40400
    assert normalize_amount("") == 0
    with pytest.raises(ValueError):
        normalize_amount("bukan-angka")


def test_normalize_date():
    assert normalize_date(date(2026, 1, 6)) == "2026-01-06"
    serial = (date(2026, 1, 6) - date(1899, 12, 30)).days
    assert normalize_date(serial) == "2026-01-06"
    assert normalize_date("6/1/2026") == "2026-01-06"
    with pytest.raises(ValueError):
        normalize_date("")


def test_normalize_bank_varian_jago():
    mapping = {"JAGO": {"account_number": "123", "pocket": "Jago"}}
    tx = {"date": "2026-01-06", "debit": 0, "credit": 1000,
          "description": "x", "counterparty": "", "balance": 5000, "time": ""}
    out = normalize_bank_transaction(
        {"bank": "Bank Jago", "account_number": "123"}, tx, mapping)
    assert out["pocket"] == "Jago"
    with pytest.raises(ValueError, match="Nomor rekening"):
        normalize_bank_transaction(
            {"bank": "Bank Jago", "account_number": "999"}, tx, mapping)


def _statement_valid():
    return {
        "bank": "BRI", "account_number": "123",
        "period_start": "2026-01-01", "period_end": "2026-01-31",
        "opening_balance": 100000, "closing_balance": 130000,
        "total_debit": 20000, "total_credit": 50000,
        "transactions": [
            {"date": "2026-01-06", "debit": 0, "credit": 50000, "balance": 150000},
            {"date": "2026-01-07", "debit": 20000, "credit": 0, "balance": 130000},
        ],
    }


def test_validate_statement_valid():
    hasil = validate_statement(_statement_valid())
    assert hasil["is_valid"], hasil["errors"]


def test_validate_statement_saldo_rusak():
    s = _statement_valid()
    s["transactions"][1]["balance"] = 999999
    s["closing_balance"] = 999999
    hasil = validate_statement(s)
    assert not hasil["is_valid"]
    assert any("balance mismatch" in e for e in hasil["errors"])


def test_push_pending_dengan_datetime(tmp_path, monkeypatch):
    # rec["tanggal"] kini datetime — json.dumps tanpa default=str TypeError
    import main
    monkeypatch.setattr(main, "PENDING", tmp_path / "p.jsonl")
    main.push_pending({"tanggal": datetime(2026, 1, 6, 14, 33), "nominal": 1000}, "uji")
    rec = json.loads(main.PENDING.read_text(encoding="utf-8").strip())
    assert rec["tanggal"].startswith("2026-01-06")
    assert rec["_error"] == "uji"


def test_qa_tgl_dengan_waktu():
    # tampilan sel date-time baru tidak membuat filter periode nihil
    assert qa._tgl("1/6/2026 14:33:12") == date(2026, 1, 6)
    assert qa._tgl("6-Jan-26 14:33") == date(2026, 1, 6)
    assert qa._tgl("6-Jan-26") == date(2026, 1, 6)
