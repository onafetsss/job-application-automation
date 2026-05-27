"""One-time Gmail OAuth2 token acquisition script.

Run this locally once to obtain an offline refresh token for the Gmail API.

Usage:
    uv run python scripts/gmail_oauth.py

Prerequisites:
    1. Create a GCP project with Gmail API enabled
    2. Create an OAuth 2.0 Client ID (Desktop app type) in GCP Console
    3. Download the client credentials JSON and set GOOGLE_CREDENTIALS_PATH in .env
    4. Optionally set GOOGLE_TOKEN_PATH in .env (defaults to .google_token.json)

The script opens a browser window for the OAuth consent flow. After approving,
it writes the token (including refresh_token) to GOOGLE_TOKEN_PATH.

Security: Never commit .google_token.json to git. It is listed in .gitignore.
"""

import os
import sys

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

# gmail.readonly scope is sufficient for reading messages — no write access needed
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def main() -> None:
    """Run the OAuth2 local server flow and write credentials to token file."""
    credentials_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
    token_path = os.environ.get("GOOGLE_TOKEN_PATH", ".google_token.json")

    if not os.path.exists(credentials_path):
        print(
            f"ERROR: Credentials file not found at '{credentials_path}'.\n"
            "Steps to fix:\n"
            "  1. Go to GCP Console -> APIs & Services -> Credentials\n"
            "  2. Create an OAuth 2.0 Client ID (Desktop app type)\n"
            "  3. Download the JSON file\n"
            f"  4. Set GOOGLE_CREDENTIALS_PATH={credentials_path} in .env\n"
            "     or place the file at 'credentials.json'",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Loading credentials from: {credentials_path}")
    print("A browser window will open for you to authorize Gmail access.")
    print("Select your Gmail account and approve the 'gmail.readonly' scope.\n")

    flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes=SCOPES)

    # access_type="offline" ensures we get a refresh_token for 24/7 unattended operation
    # prompt="consent" forces the consent screen even if previously approved — ensures refresh_token is included
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print(f"\nToken written to: {token_path}")
    print("Next steps:")
    print(f"  1. Set GOOGLE_TOKEN_PATH={token_path} in .env (or use the default)")
    print("  2. Add .google_token.json to .gitignore (NEVER commit this file)")
    print("  3. Start the API server: uv run uvicorn src.api.app:app --port 8000")
    print("  4. Test polling: curl -X POST http://localhost:8000/gmail/poll-gmail")


if __name__ == "__main__":
    main()
