import logging

logger = logging.getLogger(__name__)

WORKSHEET_TITLE = "RECONCILIATION"

HEADERS = [
    "Bank",
    "Account Number",
    "Period Start",
    "Period End",
    "Match Status",
    "Bank Date",
    "Bank Time",
    "Bank Description",
    "Debit",
    "Credit",
    "Bank Balance",
    "Sheet Date",
    "Sheet Pocket",
    "Sheet Description",
    "Sheet Debit",
    "Sheet Credit",
    "Sheet Row",
    "Ref ID",
    "Notes",
]


def get_or_create_worksheet(
    spreadsheet,
    worksheet_title=WORKSHEET_TITLE,
):
    """Get worksheet or create it if it does not exist."""

    try:
        worksheet = spreadsheet.worksheet(worksheet_title)

    except Exception as exc:
        # Only create worksheet when it genuinely does not exist.
        import gspread

        if not isinstance(exc, gspread.WorksheetNotFound):
            raise

        worksheet = spreadsheet.add_worksheet(
            title=worksheet_title,
            rows=1000,
            cols=len(HEADERS),
        )

    return worksheet


def build_report_rows(
    reconciliation_results,
    statement,
):
    """Convert reconciliation results into spreadsheet rows."""

    rows = []

    for result in reconciliation_results:

        bank_tx = result.get("bank_transaction") or {}
        sheet_tx = result.get("sheet_transaction") or {}

        row = [
            statement.get("bank", ""),
            statement.get("account_number", ""),
            statement.get("period_start", ""),
            statement.get("period_end", ""),
            result.get("status", ""),
            bank_tx.get("date", ""),
            bank_tx.get("time", ""),
            bank_tx.get("description", ""),
            bank_tx.get("debit", 0),
            bank_tx.get("credit", 0),
            bank_tx.get("balance", 0),
            sheet_tx.get("date", ""),
            sheet_tx.get("pocket", ""),
            sheet_tx.get("description", ""),
            sheet_tx.get("debit", 0),
            sheet_tx.get("credit", 0),
            sheet_tx.get("row_number", ""),
            sheet_tx.get("ref_id", ""),
            result.get("notes", ""),
        ]

        rows.append(row)

    return rows


def write_reconciliation_report(
    sheets_service,
    spreadsheet_id,
    statement,
    reconciliation_results,
    worksheet_title=WORKSHEET_TITLE,
):
    """
    Write reconciliation report.

    Existing results for the same bank, account number,
    and statement period are replaced.

    Original TRANSAKSI worksheet is never modified.
    """

    spreadsheet = sheets_service.open_by_key(spreadsheet_id)

    worksheet = get_or_create_worksheet(
        spreadsheet=spreadsheet,
        worksheet_title=worksheet_title,
    )

    # Read existing report
    existing_rows = worksheet.get(
        "A1:S",
        value_render_option="UNFORMATTED_VALUE",
    )

    if not existing_rows:
        existing_rows = [HEADERS]

    existing_headers = [
        str(value).strip()
        for value in existing_rows[0]
    ]

    if existing_headers != HEADERS:
        raise ValueError(
            f"Header worksheet {worksheet_title} tidak sesuai."
        )

    target_bank = str(statement.get("bank", "")).strip().upper()
    target_account = str(
        statement.get("account_number", "")
    ).strip()

    target_period_start = statement.get("period_start")
    target_period_end = statement.get("period_end")

    # Keep reports from other banks/accounts/periods
    retained_rows = [HEADERS]

    for row in existing_rows[1:]:

        row = row + [None] * (len(HEADERS) - len(row))

        bank = str(row[0] or "").strip().upper()
        account = str(row[1] or "").strip()
        period_start = str(row[2] or "").strip()
        period_end = str(row[3] or "").strip()

        same_report = (
            bank == target_bank
            and account == target_account
            and period_start == target_period_start
            and period_end == target_period_end
        )

        if not same_report:
            retained_rows.append(row[:len(HEADERS)])

    # Build new report
    new_rows = build_report_rows(
        reconciliation_results=reconciliation_results,
        statement=statement,
    )

    final_rows = retained_rows + new_rows

    # Replace report contents
    worksheet.clear()

    worksheet.update(
        range_name="A1",
        values=final_rows,
        value_input_option="USER_ENTERED",
    )

    logger.info(
        "Reconciliation report berhasil ditulis. "
        "Bank=%s, Account=%s, Period=%s sampai %s, "
        "Transactions=%d",
        target_bank,
        target_account,
        target_period_start,
        target_period_end,
        len(new_rows),
    )

    return len(new_rows)
