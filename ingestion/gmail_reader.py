"""
ingestion/gmail_reader.py

Fetches and parses emails from Gmail into clean Python dicts.
This is the raw data layer — no AI decisions happen here.

Each email is returned as:
{
    "id": str,              # Gmail message ID (unique)
    "thread_id": str,       # Thread this message belongs to
    "from": str,            # Sender email address
    "to": str,              # Recipient email address
    "subject": str,         # Email subject line
    "body": str,            # Plain text body (cleaned)
    "timestamp": str,       # ISO 8601 datetime string
    "labels": list[str],    # Gmail labels (INBOX, UNREAD, etc.)
    "snippet": str,         # Gmail's short preview text
}
"""

import base64
import os
import re
from datetime import datetime, timezone
from typing import Optional

from auth.gmail_auth import get_gmail_service
from dotenv import load_dotenv

load_dotenv()

FETCH_LIMIT = int(os.getenv("EMAIL_FETCH_LIMIT", 10))
EMAIL_LABEL = os.getenv("EMAIL_LABEL", "INBOX")


def fetch_emails(
    max_results: int = FETCH_LIMIT,
    label: str = EMAIL_LABEL,
    unread_only: bool = True,
) -> list[dict]:
    """
    Fetch and parse emails from Gmail.

    Args:
        max_results: Maximum number of emails to retrieve.
        label: Gmail label to filter by (e.g. "INBOX", "SENT").
        unread_only: If True, only fetch unread messages.

    Returns:
        List of parsed email dicts, newest first.
    """
    service = get_gmail_service()

    # Build query string
    query = "is:unread" if unread_only else ""

    # Get list of message IDs
    response = (
        service.users()
        .messages()
        .list(
            userId="me",
            labelIds=[label],
            q=query,
            maxResults=max_results,
        )
        .execute()
    )

    messages = response.get("messages", [])

    if not messages:
        print("No emails found.")
        return []

    # Fetch full details for each message
    parsed_emails = []
    for msg_ref in messages:
        email = _fetch_and_parse(service, msg_ref["id"])
        if email:
            parsed_emails.append(email)

    print(f"Fetched {len(parsed_emails)} emails.")
    return parsed_emails


def fetch_email_by_id(message_id: str) -> Optional[dict]:
    """
    Fetch a single email by its Gmail message ID.

    Args:
        message_id: Gmail message ID string.

    Returns:
        Parsed email dict or None if not found.
    """
    service = get_gmail_service()
    return _fetch_and_parse(service, message_id)


def _fetch_and_parse(service, message_id: str) -> Optional[dict]:
    """
    Internal: fetch full message data from Gmail API and parse it.

    Args:
        service: Authenticated Gmail API service.
        message_id: Gmail message ID.

    Returns:
        Parsed email dict or None on error.
    """
    try:
        msg = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }

        return {
            "id": msg["id"],
            "thread_id": msg["threadId"],
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "subject": headers.get("subject", "(no subject)"),
            "body": _extract_body(msg["payload"]),
            "timestamp": _parse_timestamp(headers.get("date", "")),
            "labels": msg.get("labelIds", []),
            "snippet": msg.get("snippet", ""),
        }

    except Exception as e:
        print(f"Error parsing message {message_id}: {e}")
        return None


def _extract_body(payload: dict) -> str:
    """
    Recursively extract plain text body from a Gmail message payload.
    Handles simple messages and multipart (text + html) messages.

    Args:
        payload: Gmail message payload dict.

    Returns:
        Decoded plain text string.
    """
    # Direct body data (simple message)
    if "body" in payload and payload["body"].get("data"):
        return _decode_base64(payload["body"]["data"])

    # Multipart message — walk the parts tree
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    return _decode_base64(data)
            # Recurse into nested multipart
            if "parts" in part:
                result = _extract_body(part)
                if result:
                    return result

    return ""


def _decode_base64(data: str) -> str:
    """
    Decode Gmail's URL-safe base64 encoded body content.

    Args:
        data: Base64url encoded string from Gmail API.

    Returns:
        Decoded UTF-8 string, whitespace normalized.
    """
    decoded_bytes = base64.urlsafe_b64decode(data + "==")
    text = decoded_bytes.decode("utf-8", errors="replace")
    # Normalize excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _parse_timestamp(date_str: str) -> str:
    """
    Parse email Date header into ISO 8601 format.

    Args:
        date_str: Raw Date header string from email.

    Returns:
        ISO 8601 datetime string, or raw string if parsing fails.
    """
    if not date_str:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return date_str


if __name__ == "__main__":
    import json

    emails = fetch_emails(max_results=5)
    for email in emails:
        print(json.dumps(email, indent=2, ensure_ascii=False))
        print("─" * 60)
