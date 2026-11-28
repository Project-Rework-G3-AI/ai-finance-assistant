"""SC-07: bank statement reconciliation.

Measured: whether the closing balance computed by the system matches the
closing balance printed on the statement.

The reference is read **without the model being tested**:

- BRI: the PDF has a text layer, so the closing balance and totals are read
  straight from the text.
- BNI: the PDF is a scan (0 characters of text), so the figures were read
  manually and recorded in `_sc07_bni_reference.json` together with where they
  sit on the page.

The manual BNI reference is not a shortcut. If the closing balance were read by
the same model being tested, the result would be a model compared against
itself, which measures nothing.

Run:
    python3 tests/_sc07_run.py --statements /tmp/mutasi
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _sc07_text_statement import read_bni_reference, read_text_statement  # noqa: E402

STATEMENT_DIR = Path(os.getenv("SC07_STATEMENT_DIR", str(REPO / "dataset" / "mutasi")))
BRI_FILE = "Mutasi_Rekening_BRI-Januari_2026.pdf"
BNI_FILE = "BNI_Mutasi_Januari_2026.pdf"


def _ai_env() -> tuple[str, str, str]:
    key = os.getenv("AI_API_KEY", "").strip()
    base = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    model = os.getenv("AI_MODEL", "").strip()
    return key, base, model


def _reference(filename: str, pdf_bytes: bytes) -> dict:
    """Reference that does not depend on the model."""
    if filename == BRI_FILE:
        text = read_text_statement(pdf_bytes)
        return {
            "kind": "PDF text layer",
            "independent_of_model": True,
            "account_number": text["account_number"],
            "period_start": text["period_start"],
            "period_end": text["period_end"],
            "transaction_count": text["transaction_count"],
            "opening_balance": text["opening_balance_printed"],
            "total_debit": text["total_debit_printed"],
            "total_credit": text["total_credit_printed"],
            "closing_balance": text["closing_balance_printed"],
        }

    if filename == BNI_FILE:
        reference = read_bni_reference()
        return {
            "kind": reference["source"],
            "independent_of_model": True,
            "account_number": reference["account_number"],
            "period_start": reference["period_start"],
            "period_end": reference["period_end"],
            "transaction_count": None,
            "opening_balance": reference["opening_balance"],
            "total_debit": reference["total_debit"],
            "total_credit": reference["total_credit"],
            "closing_balance": reference["closing_balance"],
            "figures_location": reference["figures_location"],
        }

    raise SystemExit(f"no reference available for {filename}")


async def measure_one(
    filename: str, pdf_bytes: bytes, key: str, base: str, model: str
) -> dict:
    """Run the production chain unchanged, then compare the closing balance."""
    import httpx

    from reconciliation.extractor import extract_bank_statement
    from reconciliation.statement_validator import validate_statement

    reference = _reference(filename, pdf_bytes)

    started = time.monotonic()
    error = ""
    statement = None
    validation = None
    try:
        async with httpx.AsyncClient() as client:
            statement = await extract_bank_statement(
                pdf_bytes=pdf_bytes, ai_key=key, ai_base=base, ai_model=model,
            )
        validation = validate_statement(statement)
    except Exception as exc:  # noqa: BLE001 - a failure is a measurement result
        error = f"{type(exc).__name__}: {exc}"
    seconds = time.monotonic() - started

    statement_closing = None
    statement_transactions = None
    if statement:
        statement_closing = statement.get("closing_balance")
        statement_transactions = len(statement.get("transactions") or [])

    reference_closing = reference["closing_balance"]
    difference = None
    if isinstance(statement_closing, (int, float)) and reference_closing is not None:
        difference = abs(float(statement_closing) - float(reference_closing))

    return {
        "file": filename,
        "reference_kind": reference["kind"],
        "reference_independent": reference["independent_of_model"],
        "account_number_reference": reference["account_number"],
        "account_number_statement": (statement or {}).get("account_number"),
        "period_reference": [reference["period_start"], reference["period_end"]],
        "period_statement": [
            (statement or {}).get("period_start"),
            (statement or {}).get("period_end"),
        ],
        "opening_balance_reference": reference["opening_balance"],
        "opening_balance_statement": (statement or {}).get("opening_balance"),
        "total_debit_reference": reference["total_debit"],
        "total_debit_statement": (statement or {}).get("total_debit"),
        "total_credit_reference": reference["total_credit"],
        "total_credit_statement": (statement or {}).get("total_credit"),
        "closing_balance_reference": reference_closing,
        "closing_balance_statement": statement_closing,
        "closing_balance_difference": difference,
        "transaction_count_reference": reference["transaction_count"],
        "transaction_count_statement": statement_transactions,
        "validation_passed": (validation or {}).get("is_valid"),
        "validation_errors": (validation or {}).get("errors", []),
        "seconds": round(seconds, 2),
        "error": error,
    }


async def measure_all(folder: Path, out: Path) -> dict:
    key, base, model = _ai_env()
    if not key:
        raise SystemExit("AI_API_KEY is not set")

    out.mkdir(parents=True, exist_ok=True)
    samples = []
    for filename in (BNI_FILE, BRI_FILE):
        path = folder / filename
        if not path.exists():
            print(f"SKIP {filename}: not found in {folder}")
            continue
        print(f"processing {filename} ({path.stat().st_size:,} bytes) ...", flush=True)
        sample = await measure_one(filename, path.read_bytes(), key, base, model)
        verdict = "MATCH" if sample["closing_balance_difference"] == 0 else (
            "MISMATCH" if sample["closing_balance_difference"] is not None else "UNREADABLE"
        )
        print(f"  closing balance system    : {sample['closing_balance_statement']}")
        print(f"  closing balance statement : {sample['closing_balance_reference']}")
        print(f"  difference                : {sample['closing_balance_difference']}  -> {verdict}")
        if sample["error"]:
            print(f"  error                     : {sample['error']}")
        samples.append(sample)

    data = {
        "model": model,
        "references_independent": all(s["reference_independent"] for s in samples),
        "samples": samples,
    }
    (out / "sc07_samples.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure SC-07: bank statement reconciliation"
    )
    parser.add_argument(
        "--statements", default=str(STATEMENT_DIR),
        help="folder holding the statement PDFs",
    )
    parser.add_argument(
        "--out", default=str(REPO / "sc-out"), help="output folder",
    )
    args = parser.parse_args()

    import asyncio

    data = asyncio.run(measure_all(Path(args.statements), Path(args.out)))

    print()
    matched = [s for s in data["samples"] if s["closing_balance_difference"] == 0]
    print(f"result: {len(matched)} of {len(data['samples'])} accounts have a matching closing balance")
    for sample in data["samples"]:
        if sample["closing_balance_difference"] != 0:
            print(f"  not matching: {sample['file']} (difference {sample['closing_balance_difference']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
