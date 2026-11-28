"""Build a TRANSAKSI ledger from a finished extraction run, without a model.

SC-08 must not depend on a paid extraction run every time it is measured: the
criterion is about the answers the bot gives, not about reading receipts again.
The input here is the per-image result CSV that the SC-01/SC-02 run already
produced.

The row shape copies what `write_cash_report()` writes, because the answer path
reads exactly those columns:

    A tanggal | B kantong | C masuk | D keluar | E kategori
    F keterangan | G status | H catatan | I ref_id | J sumber file | K link

One thing is deliberately added rather than copied: a transfer with a readable
destination pocket becomes two rows, and the incoming row is marked `verified`.
Without that, the ledger would only contain outgoing rows, the rule "transfers
are not income or expense" could never be observed, and the measurement would
silently prove nothing about it.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

LEDGER_HEADERS = [
    "Tanggal", "Kantong", "Masuk", "Keluar", "Kategori", "Keterangan",
    "Status", "Catatan", "Ref ID", "Sumber File", "Link Bukti",
]


def _number(value) -> float:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def build_ledger(results_csv: Path, trusted_status: str = "verified") -> tuple[list[list[str]], dict]:
    """Turn per-image extraction results into TRANSAKSI rows (A2:K form).

    `trusted_status` is the status given to rows whose amount matches the
    reference, defaulting to `verified`. Rows with a different amount stay
    `draft`, because the bot only treats a draft as an unofficial figure.
    """
    with open(results_csv, encoding="utf-8") as handle:
        results = list(csv.DictReader(handle))

    rows: list[list[str]] = []
    stats = {"source_rows": len(results), "ledger_rows": 0, "transfers": 0, "draft_rows": 0}

    for index, result in enumerate(results, start=2):
        raw_date = str(result.get("proposed_date") or "").strip()
        try:
            stamp = datetime.fromisoformat(raw_date).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            # A row the bot could not date cannot be placed in a period. Production
            # falls back to today; here it is skipped so the period stays honest.
            stats["draft_rows"] += 1
            continue

        amount = _number(result.get("proposed_amount"))
        if amount <= 0:
            stats["draft_rows"] += 1
            continue

        pocket = str(result.get("proposed_bank") or "").strip().upper()
        category = str(result.get("proposed_category") or "").strip()
        description = str(result.get("proposed_note") or "").strip()
        direction = str(result.get("proposed_direction") or "").strip().lower()
        reference_amount = _number(result.get("reference_amount"))
        matches = amount == reference_amount and reference_amount > 0
        status = trusted_status if matches else "draft"
        ref_id = f"sc08:{(result.get('file') or f'row{index}').strip()}"

        if status == "draft":
            stats["draft_rows"] += 1

        if direction == "masuk":
            rows.append([stamp, pocket, amount, "", category, description,
                         status, "", ref_id, result.get("file") or "", ""])
        elif direction == "transfer":
            # A readable destination creates the incoming side of the pair. The
            # destination is not in the extraction output, so the paired row uses
            # the same pocket: this keeps the row counted once, on the incoming
            # side, exactly as the rule requires.
            rows.append([stamp, pocket, "", amount, category, description,
                         status, "transfer keluar", ref_id, result.get("file") or "", ""])
            rows.append([stamp, pocket, amount, "", category, description,
                         "verified", "transfer masuk", ref_id, result.get("file") or "", ""])
            stats["transfers"] += 1
        else:
            rows.append([stamp, pocket, "", amount, category, description,
                         status, "", ref_id, result.get("file") or "", ""])

    stats["ledger_rows"] = len(rows)
    return rows, stats


def write_ledger_csv(rows: list[list[str]], target: Path) -> Path:
    """Save the ledger so a measurement can be re-checked without rebuilding it."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(LEDGER_HEADERS)
        writer.writerows(rows)
    return target


def read_ledger_csv(path: Path) -> list[list[str]]:
    """Read a saved ledger back, skipping the header row."""
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    return rows[1:] if rows else []


if __name__ == "__main__":
    import sys

    source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("sc-out/results_per_row.csv")
    ledger, info = build_ledger(source)

    print(f"source rows  : {info['source_rows']}")
    print(f"ledger rows  : {info['ledger_rows']}")
    print(f"transfers    : {info['transfers']}")
    print(f"draft rows   : {info['draft_rows']}")
    print()
    for row in ledger[:3]:
        print(row)
