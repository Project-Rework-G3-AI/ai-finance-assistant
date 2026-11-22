
import os
import asyncio

from dotenv import load_dotenv

from extractor import extract_bank_statement


load_dotenv()


async def main():

    pdf_path = "BNI_Mutasi_Januari_2026.pdf"

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    result = await extract_bank_statement(
        pdf_bytes=pdf_bytes,
        ai_key=os.getenv("AI_API_KEY"),
        ai_base=os.getenv("AI_BASE_URL"),
        ai_model=os.getenv("AI_MODEL")
    )

    with open("result.txt", "w") as f:
        f.write(result)

    print("\nBANK:", result["bank"])
    print("ACCOUNT:", result["account_number"])

    print("\nOPENING:", result["opening_balance"])
    print("CLOSING:", result["closing_balance"])

    print("\nTOTAL TRANSACTIONS:", len(result["transactions"]))

    # for transaction in result["transactions"]:
    #     print(transaction)


if __name__ == "__main__":
    asyncio.run(main())
