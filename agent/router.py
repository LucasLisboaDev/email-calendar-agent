"""
agent/router.py

Routes each AgentDecision to the correct handler based on intent.

This is the orchestration brain — it implements the conditional logic
that in n8n would be a series of IF/SWITCH nodes.

Key agentic concept: TOOL ROUTING
The router doesn't execute actions directly. It:
  1. Receives a decision from the classifier
  2. Checks if human approval is required
  3. If approval needed → queues for review
  4. If auto-approved → dispatches to the handler
  5. Logs every routing decision with a trace

This separation of concerns (classify → route → act) is the
foundation of production agentic systems.
"""

from utils.email_models import AgentDecision
from utils.logger import logger


# ── Approval queue ────────────────────────────────────────────────────────────
# In Phase 4 this will be a FastAPI endpoint.
# For now it's an in-memory list for human review.
_pending_approval: list[dict] = []


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

    # Actions that don't need approval run immediately
    if not decision.requires_approval:
        return _dispatch(email, decision)

    # Actions that need approval go to the queue
    return _queue_for_approval(email, decision)


def _dispatch(email: dict, decision: AgentDecision) -> dict:
    """
    Execute an auto-approved action immediately.

    Actions eligible for auto-dispatch (no approval needed):
    - archive: move to archive
    - mark_read: mark as read
    - flag_urgent: add urgent label
    """
    action = decision.suggested_action

    if action == "archive":
        return _handle_archive(email, decision)
    elif action == "mark_read":
        return _handle_mark_read(email, decision)
    elif action == "flag_urgent":
        return _handle_flag_urgent(email, decision)
    else:
        # Fallback — if an unexpected action slips through, queue it
        logger.warning(f"Unknown auto-action '{action}', queuing for approval")
        return _queue_for_approval(email, decision)


def _queue_for_approval(email: dict, decision: AgentDecision) -> dict:
    """
    Add an action to the pending approval queue.
    In Phase 4 this triggers a FastAPI endpoint the user can review.

    Actions that go through approval:
    - draft_reply: user reviews before sending
    - schedule_meeting: user confirms before booking
    """
    item = {
        "email_id": email["id"],
        "from": email.get("from", ""),
        "subject": email.get("subject", ""),
        "intent": decision.intent,
        "suggested_action": decision.suggested_action,
        "reasoning": decision.reasoning,
        "confidence": decision.confidence,
        "draft_reply": decision.draft_reply,
        "meeting_details": decision.meeting_details,
        "status": "pending",
    }

    _pending_approval.append(item)

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


# ── Action handlers ───────────────────────────────────────────────────────────
# These are stubs for now. In Phase 4 each handler calls the Gmail/Calendar API.
# The router doesn't care — it calls the handler and gets a result dict back.

def _handle_archive(email: dict, decision: AgentDecision) -> dict:
    """Auto-archive spam/promo emails."""
    # Phase 4: call gmail_actions.archive_email(email['id'])
    logger.info(f"[AUTO] Archiving [{email['id'][:8]}]: '{email.get('subject', '')[:40]}'")
    return {
        "status": "executed",
        "email_id": email["id"],
        "action": "archive",
        "message": "Email archived (stub — Phase 4 will call Gmail API)",
    }


def _handle_mark_read(email: dict, decision: AgentDecision) -> dict:
    """Mark FYI emails as read without taking further action."""
    # Phase 4: call gmail_actions.mark_as_read(email['id'])
    logger.info(f"[AUTO] Marking read [{email['id'][:8]}]: '{email.get('subject', '')[:40]}'")
    return {
        "status": "executed",
        "email_id": email["id"],
        "action": "mark_read",
        "message": "Email marked as read (stub — Phase 4 will call Gmail API)",
    }


def _handle_flag_urgent(email: dict, decision: AgentDecision) -> dict:
    """Flag urgent emails with a label and log for immediate attention."""
    # Phase 4: call gmail_actions.add_label(email['id'], 'URGENT')
    logger.warning(
        f"[URGENT] Flagged [{email['id'][:8]}]: "
        f"'{email.get('subject', '')[:40]}' from {email.get('from', '')}"
    )
    return {
        "status": "executed",
        "email_id": email["id"],
        "action": "flag_urgent",
        "message": "Email flagged as urgent (stub — Phase 4 will call Gmail API)",
    }


def get_pending_approvals() -> list[dict]:
    """
    Return all actions currently waiting for human approval.
    Called by the FastAPI endpoint in Phase 4.
    """
    return _pending_approval


def approve_action(email_id: str) -> dict:
    """
    Approve a queued action and mark it ready to execute.
    In Phase 4 this triggers the actual Gmail/Calendar API call.
    """
    for item in _pending_approval:
        if item["email_id"] == email_id and item["status"] == "pending":
            item["status"] = "approved"
            logger.info(f"Approved action for [{email_id[:8]}]: {item['suggested_action']}")
            return {"status": "approved", "email_id": email_id}
    return {"status": "not_found", "email_id": email_id}


def reject_action(email_id: str) -> dict:
    """Reject a queued action — no further processing."""
    for item in _pending_approval:
        if item["email_id"] == email_id and item["status"] == "pending":
            item["status"] = "rejected"
            logger.info(f"Rejected action for [{email_id[:8]}]")
            return {"status": "rejected", "email_id": email_id}
    return {"status": "not_found", "email_id": email_id}
