"""
actions/gmail_actions.py

Real Gmail API actions — this is where the agent affects the world.

Phase 1 fetched emails (read-only, safe).
Phase 4 sends, archives, and modifies emails (write, irreversible).

Every function here is called ONLY after human approval.
The agent proposes → human approves → this module executes.

Key concept: MIME email composition
Gmail's send API doesn't accept plain text — it requires a properly
formatted MIME message encoded in base64. This module handles that
complexity so the rest of the agent just calls send_reply(email, text).
"""

import base64
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from auth.gmail_auth import get_gmail_service
from utils.logger import logger


def send_reply(original_email: dict, reply_text: str) -> dict:
    """
    Send a reply to an email thread.

    Composes a proper MIME reply that threads correctly in Gmail
    (uses In-Reply-To and References headers).

    Args:
        original_email: The parsed email dict we're replying to.
        reply_text: The plain text body of the reply.

    Returns:
        Dict with status and sent message ID.
    """
    try:
        service = get_gmail_service()

        # Extract reply-to address from the original email
        from_addr = original_email.get("from", "")
        to_addr = _extract_email_address(from_addr)
        subject = original_email.get("subject", "")
        thread_id = original_email.get("thread_id", "")
        message_id = original_email.get("id", "")

        # Add Re: prefix if not already there
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        # Build MIME message
        msg = MIMEMultipart("alternative")
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg["In-Reply-To"] = message_id
        msg["References"] = message_id

        # Attach plain text part
        text_part = MIMEText(reply_text, "plain", "utf-8")
        msg.attach(text_part)

        # Encode to base64url (Gmail API requirement)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        # Send via Gmail API, threading it correctly
        result = (
            service.users()
            .messages()
            .send(
                userId="me",
                body={"raw": raw, "threadId": thread_id},
            )
            .execute()
        )

        logger.info(
            f"Reply sent to {to_addr} | "
            f"subject='{subject}' | "
            f"message_id={result['id']}"
        )

        return {
            "status": "sent",
            "message_id": result["id"],
            "to": to_addr,
            "subject": subject,
        }

    except Exception as e:
        logger.error(f"Failed to send reply: {e}")
        return {"status": "error", "error": str(e)}


def archive_email(message_id: str) -> dict:
    """
    Archive an email by removing the INBOX label.

    This moves it out of the inbox without deleting it.
    The email is still searchable and accessible in All Mail.

    Args:
        message_id: Gmail message ID.

    Returns:
        Dict with status.
    """
    try:
        service = get_gmail_service()

        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["INBOX"]},
        ).execute()

        logger.info(f"Archived message {message_id[:8]}")
        return {"status": "archived", "message_id": message_id}

    except Exception as e:
        logger.error(f"Failed to archive {message_id[:8]}: {e}")
        return {"status": "error", "error": str(e)}


def mark_as_read(message_id: str) -> dict:
    """
    Mark an email as read by removing the UNREAD label.

    Args:
        message_id: Gmail message ID.

    Returns:
        Dict with status.
    """
    try:
        service = get_gmail_service()

        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()

        logger.info(f"Marked as read: {message_id[:8]}")
        return {"status": "read", "message_id": message_id}

    except Exception as e:
        logger.error(f"Failed to mark read {message_id[:8]}: {e}")
        return {"status": "error", "error": str(e)}


def add_label(message_id: str, label_name: str) -> dict:
    """
    Add a label to an email. Creates the label if it doesn't exist.

    Args:
        message_id: Gmail message ID.
        label_name: Label name (e.g. "URGENT", "AI-Processed").

    Returns:
        Dict with status.
    """
    try:
        service = get_gmail_service()

        # Get or create the label
        label_id = _get_or_create_label(service, label_name)

        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"addLabelIds": [label_id]},
        ).execute()

        logger.info(f"Added label '{label_name}' to {message_id[:8]}")
        return {"status": "labeled", "message_id": message_id, "label": label_name}

    except Exception as e:
        logger.error(f"Failed to add label: {e}")
        return {"status": "error", "error": str(e)}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_email_address(from_str: str) -> str:
    """
    Extract clean email address from a From header string.

    Examples:
      'John Doe <john@example.com>' → 'john@example.com'
      'john@example.com'           → 'john@example.com'
    """
    if "<" in from_str and ">" in from_str:
        return from_str.split("<")[1].split(">")[0].strip()
    return from_str.strip()


def _get_or_create_label(service, label_name: str) -> str:
    """
    Get a Gmail label ID by name, creating it if it doesn't exist.

    Args:
        service: Authenticated Gmail service.
        label_name: The label name to find or create.

    Returns:
        Gmail label ID string.
    """
    # List existing labels
    labels = service.users().labels().list(userId="me").execute()
    for label in labels.get("labels", []):
        if label["name"].lower() == label_name.lower():
            return label["id"]

    # Create it if not found
    new_label = (
        service.users()
        .labels()
        .create(
            userId="me",
            body={
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        .execute()
    )
    logger.info(f"Created new Gmail label: {label_name}")
    return new_label["id"]
