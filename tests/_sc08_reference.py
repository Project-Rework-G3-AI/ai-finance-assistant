"""Independent reference for SC-08: totals computed straight from raw ledger rows.

Why this file exists
--------------------
SC-08 asks whether the answers the bot gives match the figures in the spreadsheet.
If the reference were produced by calling `cash_report.qa.aggregate`, the bot would
be compared against itself: both sides would use the same function, so the test
would only prove the function is deterministic, not that its answers are right.

So the reference parses the raw A2:K rows on its own, with its own date parser,
its own number parser, and its own period slicing, deliberately written to follow
the *rules stated in the product* rather than the production code:

1. A period is half-open: start <= date < end. A transaction on 31 January counts,
   one on 1 February does not.
2. `Transfer Antar Bank` is never income and never expense. Only the incoming
   side of a transfer pair is counted when reporting transfer volume.
3. Verified and draft are reported separately, because a draft row is not an
   official figure.
4. A row whose date cannot be read is out of every period, including the total.

Any difference between this reference and the bot is therefore a real difference
in meaning, not a shared bug.
"""
from __future__ import annotations

from datetime import date, datetime

# Stated rule, not imported from the production module: if production ever
# renames this category, the reference must disagree loudly instead of following
# along silently.
TRANSFER_CATEGORY = "Transfer Antar Bank"

DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d-%b-%y",
    "%d-%b-%Y",
    "%b %d, %Y",
)

MONTHS = {
    "jan": 1, "januari": 1, "january": 1,
    "feb": 2, "februari": 2, "february": 2,
    "mar": 3, "maret": 3, "march": 3,
    "apr": 4, "april": 4,
    "mei": 5, "may": 5,
    "jun": 6, "juni": 6, "june": 6,
    "jul": 7, "juli": 7, "july": 7,
    "agu": 8, "ags": 8, "agustus": 8, "aug": 8, "august": 8,
    "sep": 9, "september": 9,
    "okt": 10, "oktober": 10, "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "des": 12, "desember": 12, "dec": 12, "december": 12,
}


def parse_date(value) -> date | None:
    """Read a ledger date cell. Returns None when it cannot be read."""
    text = str(value or "").strip()
    if not text:
        return None

    candidates = [text]
    without_time = text.split(" ")[0]
    if without_time != text:
        candidates.append(without_time)

    for candidate in candidates:
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def parse_amount(value) -> float:
    """Read a money cell. Empty means zero; an unreadable cell is an error.

    Production treats an unreadable amount as zero, which would quietly hide a
    bad cell. Here it raises, so a broken ledger shows up as a broken reference
    instead of a plausible-looking zero.
    """
    text = str(value or "").strip()
    if not text:
        return 0.0

    cleaned = text.replace("Rp", "").replace(" ", "").replace("\u00a0", "")
    # A trailing separator is punctuation from the sentence, not part of the
    # number: "draft Rp35.000, dan sisanya" must read as 35000.
    cleaned = cleaned.rstrip(".,") or "0"
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    cleaned = cleaned.replace("-", "") if negative else cleaned

    # Indonesian format: dot for thousands, comma for decimals.
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Commas only: thousands separators when each group after the first has
        # three digits (1,932,685), otherwise an Indonesian decimal comma
        # (192643952,00).
        groups = cleaned.split(",")
        if len(groups) > 1 and all(len(g) == 3 for g in groups[1:]):
            cleaned = "".join(groups)
        elif len(groups) == 2:
            cleaned = groups[0] + "." + groups[1]
    elif "." in cleaned:
        # Dots only: they are thousands separators when every group after the
        # first has exactly three digits (1.932.685), and a decimal point
        # otherwise (192643952.00). Getting this wrong turns 1.9 million into
        # 1.932685, which would make a correct answer look wrong.
        groups = cleaned.split(".")
        if len(groups) > 1 and all(len(g) == 3 for g in groups[1:]):
            cleaned = "".join(groups)
        elif len(groups) > 2:
            cleaned = "".join(groups[:-1]) + "." + groups[-1]

    try:
        amount = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"amount cannot be read: {value!r}") from exc
    return -amount if negative else amount


def parse_period(text: str, today: date | None = None) -> tuple[date, date]:
    """Half-open period (start, end_exclusive) from '2026-01', 'Jan', or ''."""
    today = today or date.today()
    raw = (text or "").strip().lower()

    if not raw:
        year, month = today.year, today.month
    elif "-" in raw and raw.split("-")[0].isdigit():
        year_text, month_text = raw.split("-")[:2]
        year, month = int(year_text), int(month_text)
    else:
        month = MONTHS.get(raw) or MONTHS.get(raw[:3])
        if month is None:
            raise ValueError(f"period cannot be read: {text!r}")
        year = today.year

    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def read_rows(rows: list[list[str]]) -> list[dict]:
    """Turn raw A2:K rows into records this module can count."""
    records = []
    for raw in rows:
        cells = (list(raw) + [""] * 11)[:11]
        if not any(str(cell).strip() for cell in cells):
            continue
        records.append({
            "date": parse_date(cells[0]),
            "pocket": str(cells[1]).strip(),
            "in": parse_amount(cells[2]),
            "out": parse_amount(cells[3]),
            "category": str(cells[4]).strip(),
            "description": str(cells[5]).strip(),
            "status": str(cells[6]).strip().lower(),
            "ref_id": str(cells[8]).strip(),
        })
    return records


def slice_period(records: list[dict], start: date, end: date) -> list[dict]:
    """Rules 1 and 4: inside the half-open window, readable date only."""
    return [r for r in records if r["date"] is not None and start <= r["date"] < end]


def is_transfer(record: dict) -> bool:
    return record["category"].strip() == TRANSFER_CATEGORY


def totals(records: list[dict], start: date, end: date) -> dict:
    """Totals following rules 2 and 3.

    Transfers are counted on their incoming side only, and kept in a separate
    bucket. Verified and draft never mix.
    """
    inside = slice_period(records, start, end)

    result = {
        "period_start": start.isoformat(),
        "period_end_inclusive": date.fromordinal(end.toordinal() - 1).isoformat(),
        "rows_in_period": len(inside),
        "verified": {"in": 0.0, "out": 0.0, "rows": 0},
        "draft": {"in": 0.0, "out": 0.0, "rows": 0},
        "transfer": {"in": 0.0, "rows": 0},
    }

    for record in inside:
        bucket = "verified" if record["status"] == "verified" else "draft"

        if is_transfer(record):
            if record["in"] > 0:
                result["transfer"]["in"] += record["in"]
                result["transfer"]["rows"] += 1
            continue

        result[bucket]["in"] += record["in"]
        result[bucket]["out"] += record["out"]
        result[bucket]["rows"] += 1

    return result


def by_category(records: list[dict], start: date, end: date) -> list[dict]:
    """Per-category totals, transfers excluded, verified and draft kept apart.

    Income and expense are kept in separate fields and ranked separately. Adding
    them together would answer "largest expense" with a category that is large
    only because of its income, which is a different question.
    """
    grouped: dict[str, dict] = {}
    for record in slice_period(records, start, end):
        if is_transfer(record):
            continue
        name = record["category"] or "(empty)"
        entry = grouped.setdefault(name, {
            "category": name,
            "verified_in": 0.0, "verified_out": 0.0,
            "draft_in": 0.0, "draft_out": 0.0,
            "rows": 0,
        })
        bucket = "verified" if record["status"] == "verified" else "draft"
        entry[f"{bucket}_in"] += record["in"]
        entry[f"{bucket}_out"] += record["out"]
        entry["rows"] += 1

    return sorted(
        grouped.values(),
        key=lambda item: -(item["verified_out"] + item["draft_out"]),
    )
