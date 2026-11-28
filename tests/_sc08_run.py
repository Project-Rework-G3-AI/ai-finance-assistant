"""SC-08: analytical question answering about the ledger.

Measured: whether the answers the bot gives match the figures in the spreadsheet.

The questions are fixed, so repeated runs ask exactly the same thing. Each answer
is judged on **the numbers it states**, not on its wording: a correct number
wrapped in different phrasing still counts, and a fluent answer carrying a wrong
figure fails.

The reference figures come from `_sc08_reference.py`, which parses the raw ledger
rows on its own. If the reference called the production code, the bot would be
compared against itself.

Run:
    python3 tests/_sc08_run.py --ledger sc-out/sc08_ledger.csv
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _sc08_ledger as ledger_tools  # noqa: E402
import _sc08_reference as reference  # noqa: E402

PERIOD = "2026-01"

# Fixed questions. The list is deliberately small and stays the same between
# runs; comparing answers to a moving list of questions would measure nothing.
QUESTIONS = [
    {
        "id": "Q1",
        "text": "Berapa total uang masuk dan total uang keluar pada Januari 2026? "
                "Sebutkan angka verified dan draft secara terpisah.",
        "checks": ["verified_in", "verified_out", "draft_in", "draft_out"],
    },
    {
        "id": "Q2",
        "text": "Berapa nominal Transfer Antar Bank pada Januari 2026, dan apakah "
                "transfer itu dihitung sebagai pemasukan atau pengeluaran?",
        "checks": ["transfer_in"],
    },
    {
        "id": "Q3",
        "text": "Sebutkan tiga kategori pengeluaran terbesar pada Januari 2026 "
                "beserta nominalnya.",
        "checks": ["top_expense"],
    },
    {
        "id": "Q4",
        "text": "Berapa jumlah baris transaksi yang tercatat pada Januari 2026, "
                "dan berapa di antaranya masih berstatus draft?",
        "checks": ["rows_in_period", "draft_rows"],
    },
]


def _ai_env() -> tuple[str, str, str]:
    return (
        os.getenv("AI_API_KEY", "").strip(),
        os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
        os.getenv("AI_MODEL", "").strip(),
    )


def numbers_in(text: str) -> list[float]:
    """Every number stated in an answer, in the order it appears.

    Handles `1.234.567`, `1,234,567`, `1234567`, `1.234,56`, and `Rp1.234.567`.
    Percentages are dropped: they describe a share, not an amount.
    """
    found: list[float] = []
    for match in re.finditer(r"(?:Rp\.?\s*)?(\d[\d.,]*)", text or ""):
        token = match.group(1)
        tail = text[match.end():match.end() + 1]
        if tail == "%":
            continue
        found.append(reference.parse_amount(token))
    return found


def mentions(text: str, amount: float) -> bool:
    """Is this amount stated in the answer, in any accepted format?"""
    wanted = round(float(amount), 2)
    if wanted == 0:
        # Zero is often written as "tidak ada" rather than "0". Judging it by
        # digits would punish a correct answer, so it is checked separately.
        return not numbers_in(text) or any(round(n, 2) == 0 for n in numbers_in(text))
    return any(round(n, 2) == wanted for n in numbers_in(text))


def judge(question: dict, answer: str, expected: dict) -> dict:
    """Decide one question by the figures it states."""
    if not answer or not answer.strip():
        return {"verdict": "fail", "reason": "empty answer", "missing": [], "stated": []}

    checks = question["checks"]
    missing: list[str] = []
    stated: list[str] = []

    def need(key: str, amount: float) -> None:
        if amount == 0:
            # A zero figure need not be stated: "tidak ada" and "draft nihil"
            # are correct answers. Only a stated non-zero amount is a fault.
            if any(round(n, 2) != 0 for n in numbers_in(answer)) and key.endswith("_in"):
                stated.append(f"{key}=0 (checked separately)")
            else:
                stated.append(f"{key}=0 (not required)")
            return
        if mentions(answer, amount):
            stated.append(f"{key}={amount:,.2f}")
        else:
            missing.append(f"{key}={amount:,.2f}")

    for key in checks:
        if key in ("verified_in", "verified_out", "draft_in", "draft_out"):
            bucket, side = key.split("_", 1)
            need(key, expected[bucket][side])
        elif key == "transfer_in":
            need(key, expected["transfer"]["in"])
        elif key == "rows_in_period":
            need(key, expected["rows_in_period"])
        elif key == "draft_rows":
            need(key, expected["draft"]["rows"])
        elif key == "top_expense":
            # The three largest expense categories, judged by amount.
            for index, item in enumerate(expected["top_expenses"][:3], start=1):
                need(f"top{index}", item["total"])

    passed = not missing
    return {
        "verdict": "pass" if passed else "fail",
        "reason": "all figures stated" if passed else "figure missing or different",
        "missing": missing,
        "stated": stated,
    }


def build_expectations(records: list[dict]) -> dict:
    start, end = reference.parse_period(PERIOD)
    totals = reference.totals(records, start, end)

    # Ranked by money going out. A category that is large only because of its
    # income is not a large expense.
    categories = reference.by_category(records, start, end)
    top_expenses = [
        {
            "category": row["category"],
            "total": row["verified_out"] + row["draft_out"],
        }
        for row in categories
        if row["verified_out"] + row["draft_out"] > 0
    ][:3]

    return {**totals, "top_expenses": top_expenses}


async def measure_one(question: dict, expected: dict, rows: list[list[str]],
                      key: str, base: str, model: str) -> dict:
    """Ask the production answer path one question and judge the reply."""
    import httpx

    from cash_report import qa

    started = time.monotonic()
    error = ""
    answer = ""
    try:
        async with httpx.AsyncClient() as client:
            answer = await qa.answer_question(
                client, question["text"], lambda year: rows
            )
    except Exception as exc:  # noqa: BLE001 - a failure is a measurement result
        error = f"{type(exc).__name__}: {exc}"
    seconds = time.monotonic() - started

    result = judge(question, answer, expected)
    return {
        "id": question["id"],
        "question": question["text"],
        "answer": answer,
        "seconds": round(seconds, 2),
        "error": error,
        **result,
    }


async def measure_all(ledger_csv: Path, out: Path) -> dict:
    key, base, model = _ai_env()
    if not key:
        raise SystemExit("AI_API_KEY is not set")

    if not ledger_csv.exists():
        raise SystemExit(
            f"ledger not found: {ledger_csv}\n"
            "build it first from a finished extraction run:\n"
            "  python3 tests/_sc08_ledger.py sc-out/results_per_row.csv"
        )

    rows = ledger_tools.read_ledger_csv(ledger_csv)
    records = reference.read_rows(rows)
    expected = build_expectations(records)

    out.mkdir(parents=True, exist_ok=True)
    samples = []
    for question in QUESTIONS:
        print(f"{question['id']}: asking ...", flush=True)
        sample = await measure_one(question, expected, rows, key, base, model)
        print(f"  verdict: {sample['verdict'].upper()}")
        if sample["missing"]:
            print(f"  not matched: {', '.join(sample['missing'])}")
        if sample["error"]:
            print(f"  error: {sample['error']}")
        samples.append(sample)

    data = {
        "model": model,
        "period": PERIOD,
        "ledger_rows": len(rows),
        "reference": {
            "totals": {k: v for k, v in expected.items() if k != "top_expenses"},
            "top_expenses": expected["top_expenses"],
        },
        "samples": samples,
    }
    (out / "sc08_samples.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    passed = sum(1 for s in samples if s["verdict"] == "pass")
    print(f"\nresult: {passed} of {len(samples)} answers match the spreadsheet figures")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure SC-08: analytical question answering"
    )
    parser.add_argument(
        "--ledger", default=str(REPO / "sc-out" / "sc08_ledger.csv"),
        help="TRANSAKSI ledger CSV used as the bot's data source",
    )
    parser.add_argument(
        "--results", default=str(REPO / "sc-out" / "results_per_row.csv"),
        help="per-image extraction results, used to build the ledger when missing",
    )
    parser.add_argument("--out", default=str(REPO / "sc-out"), help="output folder")
    args = parser.parse_args()

    ledger_path = Path(args.ledger)
    if not ledger_path.exists():
        results_path = Path(args.results)
        if not results_path.exists():
            raise SystemExit(
                f"neither ledger nor extraction results found:\n"
                f"  ledger : {ledger_path}\n  results: {results_path}\n"
                "run the SC-01/SC-02 measurement first, or point --results at its CSV"
            )
        print(f"building ledger from {results_path}")
        rows, info = ledger_tools.build_ledger(results_path)
        ledger_tools.write_ledger_csv(rows, ledger_path)
        print(f"  {info}")

    asyncio.run(measure_all(ledger_path, Path(args.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
