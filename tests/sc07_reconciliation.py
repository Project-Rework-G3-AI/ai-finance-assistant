"""SC-07 report built from `sc07_samples.json`.

Judges one thing only: whether the closing balance computed by the system
matches the closing balance printed on the statement. The other figures are
shown as supporting detail, not as a verdict, so that two numbers with
different denominators are never blended together.
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


def _difference(value) -> str:
    if value is None:
        return "(cannot be computed)"
    if value == 0:
        return "0,00 (same)"
    return _rupiah(value)


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Column-aligned table. File names are never truncated: truncating loses evidence."""
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]

    def render(cells: list[str]) -> str:
        return "  ".join(
            cell.rjust(widths[i]) if i else cell.ljust(widths[i])
            for i, cell in enumerate(cells)
        )

    return [render(headers), render(["-" * w for w in widths])] + [render(r) for r in rows]


def write_report(out: Path) -> dict:
    path = out / "sc07_samples.json"
    if not path.exists():
        raise SystemExit(
            f"no {path}\n"
            "SC-07 measures bank statement reconciliation; run this first:\n"
            "  python3 tests/_sc07_run.py --statements <PDF folder>"
        )

    data = json.loads(path.read_text(encoding="utf-8"))
    samples = data["samples"]

    judged = [s for s in samples if s["closing_balance_difference"] is not None]
    matched = [s for s in judged if s["closing_balance_difference"] == 0]
    mismatched = [s for s in judged if s["closing_balance_difference"] != 0]
    unreadable = [s for s in samples if s["closing_balance_difference"] is None]

    passed = bool(samples) and not mismatched and not unreadable

    lines = []
    lines.append("SC-07 - Bank statement reconciliation")
    lines.append("=" * 68)
    lines.append("")
    lines.append("Target (BRD)     : closing balance matches on both accounts")
    lines.append("Judged figure    : number of accounts whose closing balance matches")
    lines.append(f"Status           : {'PASSED' if passed else 'NOT PASSED'}")
    lines.append("")
    lines.append(f"Model            : {data.get('model')}")
    lines.append(f"Reference independent : {'yes' if data.get('references_independent') else 'NO'}")
    lines.append("")

    lines.append("Result per account")
    lines.append("-" * 68)
    for sample in samples:
        verdict = "MATCH" if sample["closing_balance_difference"] == 0 else (
            "MISMATCH" if sample["closing_balance_difference"] is not None else "UNREADABLE"
        )
        lines.append(f"{sample['file']}")
        lines.append(f"  closing balance printed : {_rupiah(sample['closing_balance_reference'])}")
        lines.append(f"  closing balance system  : {_rupiah(sample['closing_balance_statement'])}")
        lines.append(f"  difference              : {_difference(sample['closing_balance_difference'])}   [{verdict}]")
        lines.append(f"  reference taken from    : {sample['reference_kind']}")
        lines.append("")

    lines.append("Supporting figures (not used to judge the target)")
    lines.append("-" * 68)
    lines += _table(
        ["file", "opening", "debit", "credit"],
        [[s["file"], _rupiah(s["opening_balance_reference"]),
          _rupiah(s["total_debit_reference"]), _rupiah(s["total_credit_reference"])]
         for s in samples],
    )
    lines.append("")
    lines.append("Figures above are those printed on the statement, not computed by the system.")
    lines.append("")

    lines.append("Reading accuracy")
    lines.append("-" * 68)
    lines += _table(
        ["file", "trx printed", "trx system", "validation"],
        [[s["file"],
          "-" if s["transaction_count_reference"] is None else str(s["transaction_count_reference"]),
          "-" if s["transaction_count_statement"] is None else str(s["transaction_count_statement"]),
          "passed" if s["validation_passed"] else "failed"]
         for s in samples],
    )
    lines.append("")

    for sample in samples:
        if sample["validation_errors"]:
            lines.append(f"Validation rejected {sample['file']}:")
            for error in sample["validation_errors"][:10]:
                lines.append(f"  - {error}")
            lines.append("")

    if unreadable:
        lines.append("Accounts that could not be judged")
        lines.append("-" * 68)
        for sample in unreadable:
            reason = sample["error"] or "closing balance unreadable from the statement"
            lines.append(f"  {sample['file']}: {reason[:150]}")
        lines.append("")

    lines.append("Notes")
    lines.append("-" * 68)
    lines.append("The BRI reference is read from the PDF text layer, without a model.")
    lines.append("The BNI reference was read manually because its PDF is a scan with no")
    lines.append("text layer; where the figures sit is recorded in _sc07_bni_reference.json.")
    lines.append("If the closing balance were read by the same model being tested, the result")
    lines.append("would be a model compared against itself, which is not a measurement.")
    lines.append("")
    lines.append("A single missing transaction shifts the closing balance, so a matching")
    lines.append("closing balance requires every transaction to be read correctly.")
    lines.append("")

    text = "\n".join(lines)

    metrics = {
        "target": "closing balance matches on both accounts",
        "account_count": len(samples),
        "judged": len(judged),
        "matched": len(matched),
        "mismatched": len(mismatched),
        "unreadable": len(unreadable),
        "passed": passed,
    }

    (out / "sc07_report.txt").write_text(text, encoding="utf-8")
    (out / "sc07_metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    return {"text": text, "metrics": metrics}


if __name__ == "__main__":
    import sys

    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "sc-out"
    print(write_report(folder)["text"])
