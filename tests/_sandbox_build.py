"""Bangun template Cash Report di folder SANDBOX, khusus uji SC-03.

`cash_report/build_template.py` aslinya memakai service account untuk Sheets.
Di mesin ini tidak ada service account, tetapi OAuth user sudah aktif dan
terbukti bisa menulis Sheets. Skrip ini menyuntikkan klien OAuth ke `main._sheets`
supaya `build_template.build()` bisa dipakai apa adanya tanpa mengubah produksi.

Dijalankan dengan environment SANDBOX, bukan folder perusahaan.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path("/tmp/vf7")
sys.path.insert(0, str(REPO))
sys.path.insert(0, "/workspace/hermes-agent/data/skills/productivity/google-workspace/scripts")

# Sandbox: folder terpisah, bukan folder perusahaan.
SANDBOX_FOLDER = "1nWbws9qVFSXUYj3r0HM253IDtIfT_GN_"
os.environ["CASH_REPORT_FOLDER_ID"] = SANDBOX_FOLDER

# Kredensial model dari .env Hermes (jangan dicetak).
kunci = {}
for baris in open("/workspace/hermes-agent/.env", errors="ignore"):
    if "=" in baris and not baris.strip().startswith("#"):
        k, _, v = baris.partition("=")
        kunci[k.strip()] = v.strip().strip('"').strip("'")
os.environ["AI_API_KEY"] = kunci.get("OPENROUTER_API_KEY", "")
os.environ["AI_BASE_URL"] = "https://openrouter.ai/api/v1"
os.environ["AI_MODEL"] = "google/gemini-3.8-flash"

import main  # noqa: E402
from google_api import get_credentials  # noqa: E402
import gspread  # noqa: E402


def _sheets_oauth():
    """Klien gspread berbasis OAuth user, menggantikan service account."""
    return gspread.authorize(get_credentials())


def _drive_oauth():
    """Klien Drive berbasis token OAuth yang sudah tersimpan.

    `main._drive()` membangun kredensialnya dari GOOGLE_OAUTH_REFRESH_TOKEN di
    .env, yang tidak ada di mesin ini. Token Hermes punya scope drive penuh,
    jadi dipakai langsung.
    """
    from googleapiclient.discovery import build as gbuild

    return gbuild("drive", "v3", credentials=get_credentials(), cache_discovery=False)


# Suntikkan sebelum build() dipanggil.
main._sheets = _sheets_oauth
main._sheet_cli = _sheets_oauth()
main._drive = _drive_oauth
main._drive_svc = _drive_oauth()

from cash_report import build_template  # noqa: E402

sid = build_template.build()
print()
print("SID =", sid)
