"""
agent/router.py

Routes each AgentDecision to the correct handler.
Phase 4 update: all stubs replaced with real Gmail + Calendar API calls.

Flow:
  auto-approved actions  → execute immediately via actions/ module
  approval-required      → persist to QueueStore, wait for human
  human approves         → execute_approved_action() fires the real API call
"""

from utils.email_models import AgentDecision
from utils.logger import logger
from utils.queue_store import queue_store


def route(email: dict, decision: AgentDecision) -> dict:
    """
    Route an email + decision to the appropriate handler.

    Args:
        email: Original parsed email dict.
        decision: AgentDecision from the classifier.

    Returns:
        Result dict describing what happened.
    """
    logger.info(
        f"Routing [{email['id'][:8]}] "
        f"intent={decision.intent} → action={decision.suggested_action}"
    )

    if not decision.requires_approval:
        return _dispatch(email, decision)

    return _queue_for_approval(email, decision)


def _dispatch(email: dict, decision: AgentDecision) -> dict:
    """Execute an auto-approved action immediately."""
    action = decision.suggested_action

    if action == "archive":
        return _handle_archive(email, decision)
    elif action == "mark_read":
        return _handle_mark_read(email, decision)
    elif action == "flag_urgent":
        return _handle_flag_urgent(email, decision)
    else:
        logger.warning(f"Unknown auto-action '{action}', queuing for approval")
        return _queue_for_approval(email, decision)


def _queue_for_approval(email: dict, decision: AgentDecision) -> dict:
    """Persist an action to the approval queue."""
    item = {
        "email_id": email["id"],
        "from": email.get("from", ""),
        "subject": email.get("subject", ""),
        "body": email.get("body", "")[:500],  # Store snippet for context
        "thread_id": email.get("thread_id", ""),
        "intent": decision.intent,
        "suggested_action": decision.suggested_action,
        "reasoning": decision.reasoning,
        "confidence": decision.confidence,
        "requires_approval": decision.requires_approval,
        "draft_reply": decision.draft_reply,
        "meeting_details": decision.meeting_details,
        "status": "pending",
    }

    queue_store.add(item)

    logger.info(
        f"Queued for approval [{email['id'][:8]}]: "
        f"{decision.suggested_action} — '{email.get('subject', '')[:40]}'"
    )

    return {
        "status": "queued",
        "email_id": email["id"],
        "action": decision.suggested_action,
        "message": f"Action '{decision.suggested_action}' queued for human approval",
    }


def execute_approved_action(email_id: str) -> dict:
    """
    Execute a previously approved action.
    Called by POST /approve/{email_id} after the user clicks Approve.

    This is the function that actually fires the Gmail/Calendar API.

    Args:
        email_id: Gmail message ID of the approved item.

    Returns:
        Execution result dict.
    """
    item = queue_store.get_by_id(email_id)
    if not item:
        return {"status": "not_found", "email_id": email_id}

    action = item.get("suggested_action")
    logger.info(f"Executing approved action: {action} for [{email_id[:8]}]")

    # Reconstruct minimal email dict from stored queue item
    email = {
        "id": item["email_id"],
        "from": item.get("from", ""),
        "subject": item.get("subject", ""),
        "body": item.get("body", ""),
        "thread_id": item.get("thread_id", ""),
    }

    # ── Execute the action ─────────────────────────────────────
    if action == "draft_reply":
        result = _execute_send_reply(email, item)

    elif action == "schedule_meeting":
        result = _execute_schedule_meeting(email, item)

    elif action == "archive":
        result = _execute_archive(email)

    elif action == "mark_read":
        result = _execute_mark_read(email)

    elif action == "flag_urgent":
        result = _execute_flag_urgent(email)

    else:
        result = {"status": "error", "error": f"Unknown action: {action}"}

    # ── Record execution result ────────────────────────────────
    queue_store.mark_executed(email_id, result)

    return result


# ── Action executors ───────────────────────────────────────────────────────────

def _execute_send_reply(email: dict, item: dict) -> dict:
    """Send the draft reply via Gmail API."""
    from actions.gmail_actions import send_reply

    draft = item.get("draft_reply", "")
    if not draft:
        return {"status": "error", "error": "No draft reply found in queue item"}

    result = send_reply(email, draft)
    if result["status"] == "sent":
        logger.info(f"Reply sent for [{email['id'][:8]}] to {result.get('to')}")
    return result


def _execute_schedule_meeting(email: dict, item: dict) -> dict:
    """Create a Google Calendar event."""
    from actions.calendar_actions import create_meeting
    import os

    meeting_details = item.get("meeting_details") or {}
    organizer = os.getenv("GMAIL_ADDRESS", "me")

    # Extract attendee email from the original sender
    from_str = email.get("from", "")
    if "<" in from_str:
        attendee = from_str.split("<")[1].split(">")[0].strip()
    else:
        attendee = from_str.strip()

    result = create_meeting(
        meeting_details=meeting_details,
        organizer_email=organizer,
        attendee_email=attendee,
    )

    if result["status"] == "created":
        logger.info(
            f"Meeting created: '{meeting_details.get('topic')}' | "
            f"start={result.get('start')} | "
            f"meet={result.get('meet_link', 'N/A')}"
        )
    return result


def _execute_archive(email: dict) -> dict:
    """Archive via Gmail API."""
    from actions.gmail_actions import archive_email
    return archive_email(email["id"])


def _execute_mark_read(email: dict) -> dict:
    """Mark as read via Gmail API."""
    from actions.gmail_actions import mark_as_read
    return mark_as_read(email["id"])


def _execute_flag_urgent(email: dict) -> dict:
    """Add URGENT label via Gmail API."""
    from actions.gmail_actions import add_label
    return add_label(email["id"], "URGENT")


# ── Queue access helpers ───────────────────────────────────────────────────────
# These are called by the FastAPI endpoints in api/app.py

def get_pending_approvals() -> list[dict]:
    """Return all pending queue items."""
    return queue_store.get_pending()


def approve_action(email_id: str) -> dict:
    """
    Approve and immediately execute a queued action.
    This replaces the Phase 3 stub that just changed a status flag.
    """
    found = queue_store.approve(email_id)
    if not found:
        return {"status": "not_found", "email_id": email_id}

    # Execute the real action now
    result = execute_approved_action(email_id)
    return {"status": "approved", "email_id": email_id, "execution": result}


def reject_action(email_id: str) -> dict:
    """Reject a queued action — no execution."""
    found = queue_store.reject(email_id)
    if not found:
        return {"status": "not_found", "email_id": email_id}
    return {"status": "rejected", "email_id": email_id}
