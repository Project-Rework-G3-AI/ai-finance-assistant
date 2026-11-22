import httpx

from pdf_processor import render_pdf_pages
from vision_extractor import extract_statement_page


async def extract_bank_statement(
    pdf_bytes: bytes,
    ai_key: str,
    ai_base: str,
    ai_model: str
) -> dict:

    pages = render_pdf_pages(pdf_bytes)

    results = []

    async with httpx.AsyncClient() as client:

        for page in pages:

            result = await extract_statement_page(
                client=client,
                image_bytes=page["image_bytes"],
                page_number=page["page_number"],
                ai_key=ai_key,
                ai_base=ai_base,
                ai_model=ai_model
            )

            results.append(result)

    # Combine page-level results
    transactions = []

    metadata = {
        "bank": None,
        "account_number": None,
        "period_start": None,
        "period_end": None,
        "opening_balance": None,
        "closing_balance": None,
        "total_debit": None,
        "total_credit": None
    }

    for page in results:

        for key in metadata:

            if metadata[key] is None and page.get(key) is not None:
                metadata[key] = page[key]

        for transaction in page["transactions"]:

            transactions.append({
                **transaction,
                "page_number": page["page_number"]
            })

    return {
        **metadata,
        "transactions": transactions,
        "pages_processed": len(pages),
        "page_results": results
    }
