"""
auth/gmail_auth.py

Handles Gmail OAuth 2.0 authentication.

Works in two modes:
  LOCAL:   Reads credentials.json and token.json from disk (dev)
  RAILWAY: Reads GOOGLE_CREDENTIALS_JSON and GOOGLE_TOKEN_JSON
           env vars. When token refreshes, automatically updates
           GOOGLE_TOKEN_JSON in Railway via the Railway API —
           no manual intervention ever needed.
"""

import os
import json
import tempfile
import httpx
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
    Auto-updates Railway env var when token refreshes.
    """
    credentials_json_str = os.getenv(CREDENTIALS_ENV)
    token_json_str = os.getenv(TOKEN_ENV)

    if credentials_json_str:
        # Railway mode
        credentials_file = _write_temp_json(credentials_json_str, "credentials")
        token_file = _write_temp_json(token_json_str, "token") if token_json_str else None
    else:
        # Local mode
        if not Path(CREDENTIALS_PATH).exists():
            raise FileNotFoundError(
                f"credentials.json not found at '{CREDENTIALS_PATH}'.\n"
                "For local dev: download from Google Cloud Console.\n"
                "For Railway: set GOOGLE_CREDENTIALS_JSON env var."
            )
        credentials_file = CREDENTIALS_PATH
        token_file = TOKEN_PATH if Path(TOKEN_PATH).exists() else None

    creds = None
    if token_file and Path(token_file).exists():
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            if credentials_json_str:
                # Railway: push new token back to Railway Variables API
                _update_railway_token(creds.to_json())
            else:
                # Local: write to file
                with open(TOKEN_PATH, "w") as f:
                    f.write(creds.to_json())
                print(f"Token saved to {TOKEN_PATH}")
        else:
            if credentials_json_str:
                raise RuntimeError(
                    "No valid token found on Railway.\n"
                    "Run locally first to generate token.json, then set "
                    "GOOGLE_TOKEN_JSON in Railway with its contents."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES
            )
            creds = flow.run_local_server(port=0)
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
            print(f"Token saved to {TOKEN_PATH}")

    return creds


def _update_railway_token(new_token_json: str) -> None:
    """
    Automatically update GOOGLE_TOKEN_JSON in Railway Variables
    whenever the OAuth token refreshes.

    Uses Railway's GraphQL API with the RAILWAY_TOKEN secret.
    After this call, the next deploy will use the fresh token —
    no manual update ever needed.
    """
    railway_token = os.getenv("RAILWAY_TOKEN")
    service_id = os.getenv("RAILWAY_SERVICE_ID")
    environment_id = os.getenv("RAILWAY_ENVIRONMENT_ID")

    if not all([railway_token, service_id, environment_id]):
        print("Railway env vars not set — token refreshed but not auto-saved.")
        print("Add RAILWAY_TOKEN to Railway Variables to enable auto-refresh.")
        return

    query = """
    mutation UpsertVariables($input: VariableCollectionUpsertInput!) {
      variableCollectionUpsert(input: $input)
    }
    """

    variables = {
        "input": {
            "projectId": os.getenv("RAILWAY_PROJECT_ID"),
            "environmentId": environment_id,
            "serviceId": service_id,
            "variables": {
                "GOOGLE_TOKEN_JSON": new_token_json
            }
        }
    }

    try:
        response = httpx.post(
            "https://backboard.railway.app/graphql/v2",
            headers={
                "Authorization": f"Bearer {railway_token}",
                "Content-Type": "application/json",
            },
            json={"query": query, "variables": variables},
            timeout=10,
        )

        data = response.json()
        if "errors" in data:
            print(f"Railway API error: {data['errors']}")
        else:
            print("✅ Token auto-refreshed and saved to Railway Variables.")

    except Exception as e:
        print(f"Failed to update Railway token: {e}")
        print("Token was refreshed in memory but not persisted.")


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


if __name__ == "__main__":
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    print(f"Authenticated as: {profile['emailAddress']}")