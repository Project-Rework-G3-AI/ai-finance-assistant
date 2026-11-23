from collections import defaultdict


def make_match_key(transaction):
    """
    Build an exact matching key.

    Description is intentionally excluded because
    bank and spreadsheet descriptions may differ.
    """

    return (
        transaction["date"],
        transaction["pocket"],
        transaction["debit"],
        transaction["credit"],
    )


def reconcile_transactions(
    bank_transactions,
    sheet_transactions,
    period_start,
    period_end,
):
    """
    Reconcile bank transactions against spreadsheet transactions.

    Matching criteria:
    - Date
    - Pocket
    - Debit
    - Credit

    Each transaction is matched at most once.

    Returns:
        list[dict]: Reconciliation results.
    """

    bank_groups = defaultdict(list)
    sheet_groups = defaultdict(list)

    # Group bank transactions by matching key
    for transaction in bank_transactions:
        key = make_match_key(transaction)
        bank_groups[key].append(transaction)

    # Only consider relevant spreadsheet transactions:
    # same pocket and within statement period.
    relevant_pockets = {
        transaction["pocket"]
        for transaction in bank_transactions
    }

    for transaction in sheet_transactions:

        if transaction["pocket"] not in relevant_pockets:
            continue

        if not (
            period_start <= transaction["date"] <= period_end
        ):
            continue

        key = make_match_key(transaction)
        sheet_groups[key].append(transaction)

    results = []

    all_keys = set(bank_groups) | set(sheet_groups)

    for key in all_keys:

        bank_group = bank_groups.get(key, [])
        sheet_group = sheet_groups.get(key, [])

        # Exactly one bank transaction and one sheet transaction
        if len(bank_group) == 1 and len(sheet_group) == 1:

            results.append({
                "status": "matched",
                "bank_transaction": bank_group[0],
                "sheet_transaction": sheet_group[0],
                "candidate_sheet_transactions": [],
                "notes": "Transaksi cocok.",
            })

        # Bank transaction exists but no matching sheet transaction
        elif bank_group and not sheet_group:

            for bank_transaction in bank_group:
                results.append({
                    "status": "bank_only",
                    "bank_transaction": bank_transaction,
                    "sheet_transaction": None,
                    "candidate_sheet_transactions": [],
                    "notes": (
                        "Transaksi ditemukan di mutasi bank "
                        "tetapi tidak ditemukan di spreadsheet."
                    ),
                })

        # Sheet transaction exists but no matching bank transaction
        elif sheet_group and not bank_group:

            for sheet_transaction in sheet_group:
                results.append({
                    "status": "sheet_only",
                    "bank_transaction": None,
                    "sheet_transaction": sheet_transaction,
                    "candidate_sheet_transactions": [],
                    "notes": (
                        "Transaksi ditemukan di spreadsheet "
                        "tetapi tidak ditemukan di mutasi bank."
                    ),
                })

        # Multiple transactions have the same matching key
        else:

            for bank_transaction in bank_group:
                results.append({
                    "status": "needs_review",
                    "bank_transaction": bank_transaction,
                    "sheet_transaction": None,
                    "candidate_sheet_transactions": sheet_group,
                    "notes": (
                        "Terdapat beberapa transaksi dengan "
                        "tanggal, kantong, dan nominal yang sama. "
                        "Perlu pemeriksaan manual."
                    ),
                })

    return results


def summarize_reconciliation(results):
    """Count reconciliation results by status."""

    summary = {
        "total": len(results),
        "matched": 0,
        "bank_only": 0,
        "sheet_only": 0,
        "needs_review": 0,
    }

    for result in results:
        status = result["status"]

        if status in summary:
            summary[status] += 1

    return summary
