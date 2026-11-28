"""SC-08 report built from `sc08_samples.json`.

Judges one thing: whether the figures stated in each answer match the
spreadsheet. Wording is not judged, so a correct figure phrased differently still
passes, and a fluent answer carrying a wrong figure fails.

The reference figures are shown next to the answers so a reader can check the
verdict without reopening the code.
"""
from __future__ import annotations

import json
from pathlib import Path


def _rupiah(value) -> str:
    """Indonesian currency format: dot for thousands, comma for decimals."""
    if value is None:
        return "(unreadable)"
    text = f"{float(value):,.2f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Column-aligned table. Answers are never truncated: truncating hides the fault."""
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]

    def render(cells: list[str]) -> str:
        return "  ".join(
            cell.rjust(widths[i]) if i else cell.ljust(widths[i])
            for i, cell in enumerate(cells)
        )

    return [render(headers), render(["-" * w for w in widths])] + [render(r) for r in rows]


def write_report(out: Path) -> dict:
    path = out / "sc08_samples.json"
    if not path.exists():
        raise SystemExit(
            f"no {path}\n"
            "SC-08 measures analytical question answering; run this first:\n"
            "  python3 tests/_sc08_run.py --ledger sc-out/sc08_ledger.csv"
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    samples = data["samples"]
    reference = data["reference"]["totals"]
    top_expenses = data["reference"]["top_expenses"]

    passed = [s for s in samples if s["verdict"] == "pass"]
    failed = [s for s in samples if s["verdict"] != "pass"]

    lines = []
    lines.append("SC-08 - Analytical question answering")
    lines.append("=" * 68)
    lines.append("")
    lines.append("Target (BRD)     : every answer matches the spreadsheet figures")
    lines.append("Judged figure    : number of fixed questions answered with the right figures")
    lines.append(f"Status           : {'PASSED' if not failed else 'NOT PASSED'}")
    lines.append(
        f"Answered         : {len(passed)} of {len(samples)} questions with the right figures"
    )
    lines.append("")
    lines.append(f"Model            : {data.get('model')}")
    lines.append(f"Period           : {data.get('period')}")
    lines.append(f"Ledger rows      : {data.get('ledger_rows')}")
    lines.append("")

    lines.append("Reference figures (computed independently from the raw ledger)")
    lines.append("-" * 68)
    lines += _table(
        ["figure", "value"],
        [
            ["verified masuk", _rupiah(reference["verified"]["in"])],
            ["verified keluar", _rupiah(reference["verified"]["out"])],
            ["draft masuk", _rupiah(reference["draft"]["in"])],
            ["draft keluar", _rupiah(reference["draft"]["out"])],
            ["draft rows", str(reference["draft"]["rows"])],
            ["rows in period", str(reference["rows_in_period"])],
            ["transfer masuk", _rupiah(reference["transfer"]["in"])],
        ],
    )
    lines.append("")
    lines.append("Largest expense categories, transfers excluded:")
    for index, item in enumerate(top_expenses, start=1):
        lines.append(f"  {index}. {item['category']} = {_rupiah(item['total'])}")
    lines.append("")
    lines.append("These figures come from their own parser, not from the answer path.")
    lines.append("If the reference called the production code, the bot would be compared")
    lines.append("against itself and the result would measure nothing.")
    lines.append("")

    lines.append("Answers")
    lines.append("-" * 68)
    for sample in samples:
        lines.append(f"{sample['id']}  [{sample['verdict'].upper()}]  {sample['seconds']}s")
        lines.append(f"  question : {sample['question']}")
        lines.append(f"  answer   : {sample['answer'] or '(empty)'}")
        if sample["missing"]:
            lines.append(f"  not matched : {', '.join(sample['missing'])}")
        if sample["stated"]:
            lines.append(f"  matched     : {', '.join(sample['stated'])}")
        if sample["error"]:
            lines.append(f"  error    : {sample['error']}")
        lines.append("")

    lines.append("What is and is not judged")
    lines.append("-" * 68)
    lines.append("Judged: whether each expected figure appears in the answer, in any")
    lines.append("accepted format (1.932.685 and 1,932,685 both count).")
    lines.append("")
    lines.append("Not judged: wording, order, phrasing, or whether the answer explains")
    lines.append("itself. A correct number in a short answer passes.")
    lines.append("")
    lines.append("A wrong figure fails even when the sentence sounds confident. That is")
    lines.append("the point: a fluent answer with a wrong number is worse than a short")
    lines.append("refusal, because the reader cannot tell.")
    lines.append("")

    text = "\n".join(lines)

    metrics = {
        "target": "every answer matches the spreadsheet figures",
        "question_count": len(samples),
        "passed": len(passed),
        "failed": len(failed),
        "is_met": not failed,
        "per_question": {
            sample["id"]: {
                "verdict": sample["verdict"],
                "seconds": sample["seconds"],
                "missing": sample["missing"],
            }
            for sample in samples
        },
    }

    (out / "sc08_report.txt").write_text(text, encoding="utf-8")
    (out / "sc08_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    return {"text": text, "metrics": metrics}


if __name__ == "__main__":
    import sys

    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "sc-out"
    print(write_report(folder)["text"])
