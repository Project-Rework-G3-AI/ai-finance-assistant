"""Buat / ulang GOOGLE_OAUTH_REFRESH_TOKEN untuk akses Google Drive (scope penuh).

Prasyarat: credentials.json (OAuth client tipe Desktop) ada di folder ini.
Jalankan:  python oauth_init.py

Browser terbuka -> login Gmail tujuan -> izinkan -> salin baris
GOOGLE_OAUTH_REFRESH_TOKEN=... dari terminal ke .env (lokal) dan
Dashboard Render.
"""

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]
BASE_DIR = Path(__file__).parent
CREDENTIALS = BASE_DIR / "credentials.json"


def main() -> None:
    if not CREDENTIALS.exists():
        raise SystemExit(
            "credentials.json tidak ditemukan di folder bot.\n"
            "Buat dulu: Google Cloud Console -> Credentials -> Create OAuth client ID "
            "-> Desktop app -> Download JSON -> simpan sebagai credentials.json"
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS), SCOPES)
    creds = flow.run_local_server(port=0)
    print("\n=== Salin baris ini ke .env (lokal) dan Dashboard Render ===")
    print("GOOGLE_OAUTH_REFRESH_TOKEN=" + creds.refresh_token)
    print("\nCatatan:")
    print("- Token lama ber-scopes drive.file TIDAK berlaku untuk fitur Cash Report.")
    print("- Token tidak kedaluwarsa selama tidak dicabut / password Gmail diganti.")


if __name__ == "__main__":
    main()
