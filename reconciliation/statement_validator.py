from datetime import date


def validate_statement(statement):
    errors = []
    transactions = statement.get("transactions", [])

    # 1. Validate required metadata
    required_fields = [
        "bank",
        "account_number",
        "period_start",
        "period_end",
        "opening_balance",
        "closing_balance",
        "total_debit",
        "total_credit",
        "transactions",
    ]

    for field in required_fields:
        if field not in statement:
            errors.append(f"Missing required field: {field}")

    if errors:
        return {"is_valid": False, "errors": errors}

    # 2. Validate statement period
    try:
        period_start = date.fromisoformat(statement["period_start"])
        period_end = date.fromisoformat(statement["period_end"])

        if period_start > period_end:
            errors.append("period_start is after period_end")

    except (ValueError, TypeError):
        errors.append("Invalid statement period format")

    # 3. Validate transaction fields and amounts
    for index, transaction in enumerate(transactions, start=1):
        debit = transaction.get("debit")
        credit = transaction.get("credit")
        balance = transaction.get("balance")

        if not isinstance(debit, int) or debit < 0:
            errors.append(f"Transaction {index}: invalid debit")

        if not isinstance(credit, int) or credit < 0:
            errors.append(f"Transaction {index}: invalid credit")

        if debit == 0 and credit == 0:
            errors.append(
                f"Transaction {index}: debit and credit are both zero"
            )

        if debit > 0 and credit > 0:
            errors.append(
                f"Transaction {index}: debit and credit are both non-zero"
            )

        if not isinstance(balance, int):
            errors.append(f"Transaction {index}: invalid balance")

        try:
            transaction_date = date.fromisoformat(
                transaction["date"]
            )

            if not (
                period_start <= transaction_date <= period_end
            ):
                errors.append(
                    f"Transaction {index}: date outside statement period"
                )

        except (ValueError, TypeError, KeyError):
            errors.append(f"Transaction {index}: invalid date")

    # 4. Validate transaction totals
    calculated_debit = sum(
        tx["debit"] for tx in transactions
        if isinstance(tx.get("debit"), int)
    )

    calculated_credit = sum(
        tx["credit"] for tx in transactions
        if isinstance(tx.get("credit"), int)
    )

    if calculated_debit != statement["total_debit"]:
        errors.append(
            f"Debit total mismatch: "
            f"calculated={calculated_debit}, "
            f"statement={statement['total_debit']}"
        )

    if calculated_credit != statement["total_credit"]:
        errors.append(
            f"Credit total mismatch: "
            f"calculated={calculated_credit}, "
            f"statement={statement['total_credit']}"
        )

    # 5. Validate running balance
    previous_balance = statement["opening_balance"]

    for index, transaction in enumerate(transactions, start=1):
        debit = transaction.get("debit")
        credit = transaction.get("credit")
        balance = transaction.get("balance")

        if not all(isinstance(x, int) for x in
                   [debit, credit, balance]):
            continue

        expected_balance = previous_balance + credit - debit

        if expected_balance != balance:
            errors.append(
                f"Transaction {index}: balance mismatch. "
                f"Expected={expected_balance}, actual={balance}"
            )

        previous_balance = balance

    # 6. Validate closing balance
    if transactions:
        last_balance = transactions[-1].get("balance")

        if last_balance != statement["closing_balance"]:
            errors.append(
                f"Closing balance mismatch: "
                f"last_transaction={last_balance}, "
                f"statement={statement['closing_balance']}"
            )

    # 7. Validate overall balance equation
    expected_closing = (
        statement["opening_balance"]
        + statement["total_credit"]
        - statement["total_debit"]
    )

    if expected_closing != statement["closing_balance"]:
        errors.append(
            f"Statement balance mismatch: "
            f"calculated={expected_closing}, "
            f"statement={statement['closing_balance']}"
        )

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "calculated_debit": calculated_debit,
        "calculated_credit": calculated_credit,
    }
  