import os
import logging

from googleapiclient.errors import HttpError


logger = logging.getLogger(__name__)

CR_FOLDER_ID = os.getenv("CASH_REPORT_FOLDER_ID")

SPREADSHEET_NAME = "Cash Report 2026"
WORKSHEET_TITLE = "TRANSAKSI"

EXPECTED_HEADERS = [
    "tanggal",
    "kantong",
    "masuk",
    "keluar",
    "kategori",
    "keterangan",
    "status",
    "catatan",
    "ref id",
    "sumber file",
    "link bukti",
]


def normalize_header(header):
    """Normalize spreadsheet header for comparison."""
    return " ".join(str(header).strip().lower().split())



def find_folder_id(drive_service, folder_name, parent_folder_id):
    """Find a folder inside another Google Drive folder."""

    query = (
        f"'{parent_folder_id}' in parents "
        f"and name = '{folder_name}' "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )

    response = drive_service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name)",
        pageSize=100,
    ).execute()

    folders = response.get("files", [])

    if not folders:
        raise FileNotFoundError(
            f"Folder '{folder_name}' tidak ditemukan."
        )

    if len(folders) > 1:
        raise RuntimeError(
            f"Ditemukan lebih dari satu folder '{folder_name}'."
        )

    return folders[0]["id"]


def find_cash_report_spreadsheet_id(
    drive_service,
    statement,
    folder_id=None,
):
    """
    Find Cash Report spreadsheet based on statement period.
    """

    folder_id = folder_id or CR_FOLDER_ID

    if not folder_id:
        raise ValueError("CR_FOLDER_ID belum dikonfigurasi.")

    period_start = statement.get("period_start")

    if not period_start:
        raise ValueError("period_start tidak ditemukan dalam statement.")

    year = period_start[:4]

    year_folder_id = find_folder_id(
        drive_service=drive_service,
        folder_name=year,
        parent_folder_id=folder_id,
    )

    spreadsheet_id = find_spreadsheet_in_folder(
        drive_service=drive_service,
        folder_id=year_folder_id,
        spreadsheet_name=f"Cash Report {year}",
    )

    return spreadsheet_id


def find_spreadsheet_in_folder(
    drive_service,
    folder_id,
    spreadsheet_name,
):
    """Find a Google Spreadsheet inside a specified folder."""

    query = (
        f"'{folder_id}' in parents "
        f"and name = '{spreadsheet_name}' "
        "and mimeType = 'application/vnd.google-apps.spreadsheet' "
        "and trashed = false"
    )

    response = drive_service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name)",
        pageSize=100,
    ).execute()

    files = response.get("files", [])

    if not files:
        raise FileNotFoundError(
            f"Spreadsheet '{spreadsheet_name}' tidak ditemukan."
        )

    if len(files) > 1:
        raise RuntimeError(
            f"Ditemukan lebih dari satu spreadsheet "
            f"'{spreadsheet_name}'."
        )

    return files[0]["id"]



def read_cash_transactions(
    sheets_service,
    spreadsheet_id,
    worksheet_title=WORKSHEET_TITLE,
):
    """
    Read all transactions from the Cash Report worksheet.

    Returns:
        list[dict]: Transactions with original spreadsheet row numbers.
    """

    # Open spreadsheet using gspread
    spreadsheet = sheets_service.open_by_key(spreadsheet_id)

    # Get worksheet
    worksheet = spreadsheet.worksheet(worksheet_title)

    # Read values using raw/unformatted values
    rows = worksheet.get(
        "A1:K",
        value_render_option="UNFORMATTED_VALUE",
    )

    if not rows:
        raise ValueError(
            f"Worksheet '{worksheet_title}' kosong."
        )

    headers = [
        normalize_header(value)
        for value in rows[0]
    ]

    if headers != EXPECTED_HEADERS:
        raise ValueError(
            "Struktur header spreadsheet tidak sesuai.\n"
            f"Expected: {EXPECTED_HEADERS}\n"
            f"Actual: {headers}"
        )

    transactions = []

    for row_number, row in enumerate(rows[1:], start=2):

        # Skip completely empty rows
        if not any(
            value is not None and str(value).strip()
            for value in row
        ):
            continue

        # Pad missing trailing columns
        row = row + [None] * (
            len(EXPECTED_HEADERS) - len(row)
        )

        transaction = {
            "tanggal": row[0],
            "kantong": row[1],
            "masuk": row[2],
            "keluar": row[3],
            "kategori": row[4],
            "keterangan": row[5],
            "status": row[6],
            "catatan": row[7],
            "ref_id": row[8],
            "sumber_file": row[9],
            "link_bukti": row[10],
            "row_number": row_number,
        }

        transactions.append(transaction)

    logger.info(
        "Berhasil membaca %d transaksi dari worksheet %s.",
        len(transactions),
        worksheet_title,
    )

    return transactions


def get_cash_report_transactions(
    drive_service,
    sheets_service,
    statement,
):
    spreadsheet_id = find_cash_report_spreadsheet_id(
        drive_service=drive_service,
        statement=statement,
    )

    transactions = read_cash_transactions(
        sheets_service=sheets_service,
        spreadsheet_id=spreadsheet_id,
    )

    return spreadsheet_id, transactions