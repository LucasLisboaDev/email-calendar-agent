"""
auth/gmail_auth.py

Handles Gmail OAuth 2.0 authentication.
- First run: opens a browser window for the user to log in and grant permissions.
- Subsequent runs: loads the saved token and refreshes it automatically if expired.
- Returns an authenticated Gmail API service object ready to use.
"""

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

# Scopes define what the agent is allowed to do on behalf of the user.
# Changing these requires deleting token.json and re-authenticating.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]

CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json")


def get_gmail_service():
    """
    Authenticate and return an authorized Gmail API service.

    Flow:
      1. If token.json exists and is valid → use it directly.
      2. If token.json is expired → refresh it silently.
      3. If no token exists → open browser for user login, then save token.

    Returns:
        googleapiclient.discovery.Resource: Authenticated Gmail service.
    """
    creds = _load_or_refresh_credentials()
    service = build("gmail", "v1", credentials=creds)
    return service


def get_calendar_service():
    """
    Authenticate and return an authorized Google Calendar API service.
    Uses the same credentials/token as Gmail — single OAuth flow for both.

    Returns:
        googleapiclient.discovery.Resource: Authenticated Calendar service.
    """
    creds = _load_or_refresh_credentials()
    service = build("calendar", "v3", credentials=creds)
    return service


def _load_or_refresh_credentials() -> Credentials:
    """
    Internal helper: load existing credentials or run the OAuth flow.

    Returns:
        google.oauth2.credentials.Credentials: Valid credentials object.

    Raises:
        FileNotFoundError: If credentials.json is missing.
    """
    if not Path(CREDENTIALS_PATH).exists():
        raise FileNotFoundError(
            f"credentials.json not found at '{CREDENTIALS_PATH}'.\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )

    creds = None

    # Load saved token if it exists
    if Path(TOKEN_PATH).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # If no valid credentials, refresh or re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Silently refresh the access token using the stored refresh token
            creds.refresh(Request())
        else:
            # First-time login: open browser for user consent
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())
        print(f"Token saved to {TOKEN_PATH}")

    return creds


if __name__ == "__main__":
    # Quick test: authenticate and print the authenticated user's email
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    print(f"Authenticated as: {profile['emailAddress']}")
    print(f"Total messages: {profile['messagesTotal']}")
