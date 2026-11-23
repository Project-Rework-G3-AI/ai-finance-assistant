from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation


def normalize_date(value):
    """
    Convert date values from Google Sheets or bank statements
    into YYYY-MM-DD.
    """

    if value is None or value == "":
        raise ValueError("Tanggal tidak boleh kosong.")

    # Python datetime
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")

    # Python date
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")

    # Google Sheets serial date
    if isinstance(value, (int, float)):
        base_date = datetime(1899, 12, 30)
        converted = base_date + timedelta(days=float(value))
        return converted.strftime("%Y-%m-%d")

    value = str(value).strip()

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    raise ValueError(f"Format tanggal tidak dikenali: {value}")


def normalize_amount(value):
    """
    Convert monetary values into integer Rupiah.

    Empty values become zero.
    """

    if value is None or str(value).strip() == "":
        return 0

    if isinstance(value, bool):
        raise ValueError("Nilai nominal tidak valid.")

    if isinstance(value, (int, float, Decimal)):
        amount = Decimal(str(value))
    else:
        value = str(value).strip()
        value = (
            value.replace("Rp", "")
            .replace("rp", "")
            .replace(" ", "")
        )

        # Indonesian number format: 1.500.000
        value = value.replace(".", "").replace(",", "")

        try:
            amount = Decimal(value)
        except InvalidOperation:
            raise ValueError(f"Nominal tidak valid: {value}")

    if not amount.is_finite():
        raise ValueError("Nominal harus berupa angka finite.")

    if amount != amount.to_integral_value():
        raise ValueError(f"Nominal harus berupa Rupiah bulat: {amount}")

    return int(amount)


def normalize_text(value):
    """Normalize text fields without changing their meaning."""

    if value is None:
        return ""

    return " ".join(str(value).strip().split())


def normalize_bank_transaction(
    statement,
    transaction,
    account_mapping,
):
    """
    Normalize one bank transaction.

    account_mapping example:
    {
        "BNI": {
            "account_number": "1783680837",
            "pocket": "BNI"
        }
    }
    """

    bank = normalize_text(statement.get("bank")).upper()
    account_number = normalize_text(
        statement.get("account_number")
    )

    if bank not in account_mapping:
        raise ValueError(
            f"Bank '{bank}' belum tersedia dalam ACCOUNT_MAPPING."
        )

    mapping = account_mapping[bank]

    if account_number != normalize_text(
        mapping.get("account_number")
    ):
        raise ValueError(
            f"Nomor rekening tidak sesuai mapping untuk {bank}."
        )

    debit = normalize_amount(transaction.get("debit"))
    credit = normalize_amount(transaction.get("credit"))

    if debit < 0 or credit < 0:
        raise ValueError("Debit dan kredit tidak boleh negatif.")

    if debit > 0 and credit > 0:
        raise ValueError(
            "Transaksi tidak boleh memiliki debit dan kredit sekaligus."
        )

    if debit == 0 and credit == 0:
        raise ValueError(
            "Transaksi harus memiliki debit atau kredit."
        )

    return {
        "source": "bank",
        "bank": bank,
        "account_number": account_number,
        "date": normalize_date(transaction.get("date")),
        "pocket": normalize_text(mapping.get("pocket")),
        "debit": debit,
        "credit": credit,
        "description": normalize_text(
            transaction.get("description")
        ),
        "counterparty": normalize_text(
            transaction.get("counterparty")
        ),
        "balance": normalize_amount(
            transaction.get("balance")
        ),
        "time": normalize_text(transaction.get("time")),
        "page_number": transaction.get("page_number"),
    }


def normalize_sheet_transaction(transaction):
    """
    Normalize one transaction from Google Sheets.
    """

    debit = normalize_amount(transaction.get("keluar"))
    credit = normalize_amount(transaction.get("masuk"))

    if debit < 0 or credit < 0:
        raise ValueError("Debit dan kredit tidak boleh negatif.")

    if debit > 0 and credit > 0:
        raise ValueError(
            "Transaksi spreadsheet memiliki debit dan kredit sekaligus."
        )

    if debit == 0 and credit == 0:
        raise ValueError(
            "Transaksi spreadsheet tidak memiliki nominal."
        )

    return {
        "source": "sheet",
        "date": normalize_date(transaction.get("tanggal")),
        "pocket": normalize_text(transaction.get("kantong")),
        "debit": debit,
        "credit": credit,
        "category": normalize_text(transaction.get("kategori")),
        "description": normalize_text(
            transaction.get("keterangan")
        ),
        "notes": normalize_text(transaction.get("catatan")),
        "ref_id": normalize_text(transaction.get("ref_id")),
        "source_file": normalize_text(
            transaction.get("sumber_file")
        ),
        "evidence_link": normalize_text(
            transaction.get("link_bukti")
        ),
        "row_number": transaction.get("row_number"),
    }


def normalize_statement(statement, account_mapping):
    """
    Normalize all transactions from a bank statement.
    """

    normalized_transactions = []

    for transaction in statement.get("transactions", []):
        normalized_transactions.append(
            normalize_bank_transaction(
                statement=statement,
                transaction=transaction,
                account_mapping=account_mapping,
            )
        )

    return normalized_transactions


def normalize_sheet_transactions(transactions):
    """
    Normalize all transactions from Google Sheets.

    Invalid rows are skipped and returned as errors.
    """

    normalized_transactions = []
    errors = []

    for transaction in transactions:
        try:
            normalized_transactions.append(
                normalize_sheet_transaction(transaction)
            )
        except (ValueError, TypeError) as exc:
            errors.append({
                "row_number": transaction.get("row_number"),
                "error": str(exc),
            })

    return normalized_transactions, errors
