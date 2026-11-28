"""Read a bank statement from the PDF text layer, without a model.

Used as the SC-07 reference. For BRI the PDF prints its own summary (opening
balance, total debit, total credit, closing balance), so the reference does not
depend on the model being tested.

The BNI PDF has no text layer (scanned), so its reference is read separately
and recorded in `_sc07_bni_reference.json` together with the page it came from.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf


ROW_PATTERN = re.compile(
    r"(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2}:\d{2})\s*\n"
    r"(.+?)\n"
    r"([\d,]*)\s*\n"                     # teller / user id, may be empty
    r"([\d,]+\.\d{2})\s*\n"              # debit
    r"([\d,]+\.\d{2})\s*\n"              # credit
    r"([\d,]+\.\d{2})",                  # balance
    re.S,
)

SUMMARY_PATTERN = re.compile(
    r"Saldo Awal\s*\nOpening Balance\s*\n"
    r"Total Transaksi Debet\s*\nTotal Debit Transaction\s*\n"
    r"Total Transaksi Kredit\s*\nTotal Credit Transaction\s*\n"
    r"Saldo Akhir\s*\nClosing Balance\s*\n"
    r"([\d,]+\.\d{2})\s*\n"      # opening balance
    r"([\d,]+\.\d{2})\s*\n"      # total debit
    r"([\d,]+\.\d{2})\s*\n"      # total credit
    r"([\d,]+\.\d{2})",          # closing balance
)
SUMMARY_ORDER = ("opening_balance", "total_debit", "total_credit", "closing_balance")


def _number(text: str) -> float:
    return float(text.replace(",", ""))


def _account_number(text: str) -> str | None:
    match = re.search(r"Account No\s*\n?\s*:\s*(\d+)", text)
    if match:
        return match.group(1)
    match = re.search(r":\s*(\d{10,})", text)
    return match.group(1) if match else None


def _period(text: str) -> tuple[str | None, str | None]:
    match = re.search(r"(\d{2}/\d{2}/\d{2})\s*-\s*(\d{2}/\d{2}/\d{2})", text)
    if not match:
        return None, None

    def convert(value: str) -> str:
        day, month, year = value.split("/")
        return f"20{year}-{month}-{day}"

    return convert(match.group(1)), convert(match.group(2))


def read_text_statement(pdf_bytes: bytes) -> dict:
    """Read transactions and the printed summary from the PDF text layer."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        pages = [page.get_text() for page in document]
    text = "\n".join(pages)

    transactions = []
    for date, clock, description, teller, debit, credit, balance in ROW_PATTERN.findall(text):
        day, month, year = date.split("/")
        transactions.append({
            "date": f"20{year}-{month}-{day}",
            "time": clock,
            "description": " ".join(description.split()),
            "teller": teller.strip(),
            "debit": _number(debit),
            "credit": _number(credit),
            "balance": _number(balance),
        })

    summary = {key: None for key in SUMMARY_ORDER}
    match = SUMMARY_PATTERN.search(text)
    if match:
        for key, value in zip(SUMMARY_ORDER, match.groups()):
            summary[key] = _number(value)

    period_start, period_end = _period(text)

    return {
        "source": "PDF text layer",
        "has_text_layer": True,
        "page_count": len(pages),
        "account_number": _account_number(text),
        "period_start": period_start,
        "period_end": period_end,
        "transaction_count": len(transactions),
        "transactions": transactions,
        "opening_balance_printed": summary["opening_balance"],
        "total_debit_printed": summary["total_debit"],
        "total_credit_printed": summary["total_credit"],
        "closing_balance_printed": summary["closing_balance"],
    }


def read_bni_reference(path: Path | None = None) -> dict:
    """BNI reference read independently from the model (the PDF is scanned)."""
    path = path or Path(__file__).with_name("_sc07_bni_reference.json")
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


if __name__ == "__main__":
    import sys

    with open(sys.argv[1], "rb") as handle:
        result = read_text_statement(handle.read())

    print(f"account number   : {result['account_number']}")
    print(f"period           : {result['period_start']} to {result['period_end']}")
    print(f"transactions     : {result['transaction_count']}")
    print(f"opening printed  : {result['opening_balance_printed']:,.2f}")
    print(f"debit printed    : {result['total_debit_printed']:,.2f}")
    print(f"credit printed   : {result['total_credit_printed']:,.2f}")
    print(f"closing printed  : {result['closing_balance_printed']:,.2f}")
    print()
    for row in result["transactions"]:
        print(f"{row['date']} {row['time']}  D={row['debit']:>13,.2f} "
              f"K={row['credit']:>11,.2f} S={row['balance']:>15,.2f}  {row['description'][:40]}")
