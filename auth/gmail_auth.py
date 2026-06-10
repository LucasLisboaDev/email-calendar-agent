"""
auth/gmail_auth.py

Handles Gmail OAuth 2.0 authentication.

Works in two modes:
  LOCAL:   Reads credentials.json and token.json from disk (dev)
  RAILWAY: Reads GOOGLE_CREDENTIALS_JSON and GOOGLE_TOKEN_JSON
           env vars (production — no files on server)

The mode is detected automatically — no config needed.
"""

import os
import json
import tempfile
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]

CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json")

# Railway env var names
CREDENTIALS_ENV = "GOOGLE_CREDENTIALS_JSON"
TOKEN_ENV = "GOOGLE_TOKEN_JSON"


def get_gmail_service():
    """Authenticate and return an authorized Gmail API service."""
    creds = _load_or_refresh_credentials()
    return build("gmail", "v1", credentials=creds)


def get_calendar_service():
    """Authenticate and return an authorized Google Calendar API service."""
    creds = _load_or_refresh_credentials()
    return build("calendar", "v3", credentials=creds)


def _load_or_refresh_credentials() -> Credentials:
    """
    Load credentials from env vars (Railway) or files (local).

    Priority:
      1. GOOGLE_CREDENTIALS_JSON env var → write to temp file → use
      2. credentials.json file on disk → use directly
    """
    # ── Resolve credentials source ─────────────────────────────
    credentials_json_str = os.getenv(CREDENTIALS_ENV)
    token_json_str = os.getenv(TOKEN_ENV)

    if credentials_json_str:
        # Railway mode — write env var contents to temp files
        credentials_file = _write_temp_json(credentials_json_str, "credentials")
        token_file = _write_temp_json(token_json_str, "token") if token_json_str else None
    else:
        # Local mode — use files from disk
        if not Path(CREDENTIALS_PATH).exists():
            raise FileNotFoundError(
                f"credentials.json not found at '{CREDENTIALS_PATH}'.\n"
                "For local dev: download from Google Cloud Console.\n"
                "For Railway: set GOOGLE_CREDENTIALS_JSON env var."
            )
        credentials_file = CREDENTIALS_PATH
        token_file = TOKEN_PATH if Path(TOKEN_PATH).exists() else None

    # ── Load and refresh credentials ───────────────────────────
    creds = None

    if token_file and Path(token_file).exists():
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            _save_token(creds, token_json_str)
        else:
            if credentials_json_str:
                # Railway: can't open a browser — token must be pre-set
                raise RuntimeError(
                    "No valid token found on Railway.\n"
                    "Run locally first to generate token.json, then set "
                    "GOOGLE_TOKEN_JSON in Railway with its contents."
                )
            # Local: open browser for login
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES
            )
            creds = flow.run_local_server(port=0)
            _save_token(creds, None)
            print(f"Token saved to {TOKEN_PATH}")

    return creds


def _write_temp_json(json_str: str, prefix: str) -> str:
    """Write a JSON string to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"agent_{prefix}_",
        delete=False,
    )
    tmp.write(json_str)
    tmp.flush()
    tmp.close()
    return tmp.name


def _save_token(creds: Credentials, existing_env_value: str):
    """Save refreshed credentials to file (local) or log for Railway."""
    if existing_env_value:
        # On Railway — log the new token so the user can update the env var
        print("Token refreshed. Update GOOGLE_TOKEN_JSON in Railway with:")
        print(creds.to_json())
    else:
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())


if __name__ == "__main__":
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    print(f"Authenticated as: {profile['emailAddress']}")