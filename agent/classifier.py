"""
agent/classifier.py

Classifies incoming emails using GPT-4o function calling.
Returns a structured AgentDecision for each email.

This is the core of Phase 2 — the LLM doesn't return freeform text here.
It uses function calling to return structured JSON, which means:
  - Output is always machine-readable
  - No prompt parsing required
  - Deterministic schema enforced by the API

Key agentic concept: STRUCTURED OUTPUT via function calling.
The model reasons about the email and calls classify_email() with
its decision. We receive JSON, not prose.
"""

import os
import json
from openai import OpenAI
from dotenv import load_dotenv

from utils.email_models import AgentDecision
from utils.logger import logger
from ingestion.html_cleaner import clean_email_body

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── System prompt ─────────────────────────────────────────────────────────────
# This is the agent's persona and instructions.
# Clear, specific prompts produce consistent, accurate classifications.

SYSTEM_PROMPT = """You are an intelligent email assistant. Your job is to read 
incoming emails and classify them so an automation agent can take the right action.

Classify each email into exactly one of these intents:
- meeting_request: The sender wants to schedule a meeting, call, or sync
- reply_needed: The email requires a direct response or answer
- spam_promo: Marketing emails, newsletters, promotions, or unsolicited content
- fyi: Informational emails that need no response (receipts, notifications, updates)
- urgent: Time-sensitive emails requiring immediate attention

Rules:
- Be conservative with "urgent" — only use it if the email is genuinely time-sensitive
- Promotional emails with deals or offers are always "spam_promo"
- Automated system emails (receipts, shipping, confirmations) are "fyi"
- When in doubt between reply_needed and fyi, choose reply_needed

Always call the classify_email function with your decision."""

# ── Tool definition ───────────────────────────────────────────────────────────
# This is what GPT-4o will "call" — it forces structured output.
# The schema defines exactly what fields the model must return.

CLASSIFY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "classify_email",
            "description": "Classify an email and decide what action to take",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": [
                            "meeting_request",
                            "reply_needed",
                            "spam_promo",
                            "fyi",
                            "urgent",
                        ],
                        "description": "The classified intent of the email",
                    },
                    "suggested_action": {
                        "type": "string",
                        "enum": [
                            "schedule_meeting",
                            "draft_reply",
                            "archive",
                            "mark_read",
                            "flag_urgent",
                        ],
                        "description": "The action the agent should take",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "1-2 sentence explanation of the classification decision",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence score between 0.0 and 1.0",
                    },
                    "requires_approval": {
                        "type": "boolean",
                        "description": "Whether human approval is needed before executing the action",
                    },
                    "draft_reply": {
                        "type": "string",
                        "description": "A short draft reply if the action is draft_reply. Omit for other actions.",
                    },
                    "meeting_details": {
                        "type": "object",
                        "description": "Parsed meeting details if the action is schedule_meeting",
                        "properties": {
                            "proposed_time": {"type": "string"},
                            "duration_minutes": {"type": "integer"},
                            "topic": {"type": "string"},
                            "attendees": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
                "required": [
                    "intent",
                    "suggested_action",
                    "reasoning",
                    "confidence",
                    "requires_approval",
                ],
            },
        },
    }
]

# ── Intent → action mapping ───────────────────────────────────────────────────
# These are the default approval rules.
# Actions that affect the outside world (sending, booking) require approval.
# Read-only actions (archive, mark_read) can be automatic.

APPROVAL_REQUIRED = {
    "schedule_meeting": True,
    "draft_reply": True,
    "archive": False,
    "mark_read": False,
    "flag_urgent": False,
}


def classify_email(email: dict) -> AgentDecision:
    """
    Classify a single email using GPT-4o function calling.

    Args:
        email: Parsed email dict from gmail_reader.py

    Returns:
        AgentDecision with intent, action, and optional draft content.

    Raises:
        ValueError: If the model returns an unexpected response format.
    """
    # Clean the body before sending to the LLM
    clean_body = clean_email_body(email.get("body", ""))
    snippet = email.get("snippet", "")

    # Build the user message — give the model enough context to decide
    user_message = f"""Classify this email:

From: {email.get('from', '')}
Subject: {email.get('subject', '(no subject)')}
Labels: {', '.join(email.get('labels', []))}

Body:
{clean_body or snippet or '(no body content)'}"""

    logger.debug(f"Classifying email: {email.get('subject', '')[:60]}")

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            tools=CLASSIFY_TOOL,
            tool_choice={"type": "function", "function": {"name": "classify_email"}},
            temperature=0.1,  # Low temp = more consistent classification
            max_tokens=500,
        )

        # Extract the function call arguments
        tool_call = response.choices[0].message.tool_calls[0]
        args = json.loads(tool_call.function.arguments)

        # Apply approval rules from our config (override model's suggestion)
        action = args.get("suggested_action", "mark_read")
        requires_approval = APPROVAL_REQUIRED.get(action, True)

        decision = AgentDecision(
            email_id=email["id"],
            intent=args["intent"],
            suggested_action=action,
            reasoning=args.get("reasoning", ""),
            confidence=args.get("confidence", 1.0),
            requires_approval=requires_approval,
            draft_reply=args.get("draft_reply"),
            meeting_details=args.get("meeting_details"),
        )

        logger.info(
            f"Classified [{email['id'][:8]}] "
            f"'{email.get('subject', '')[:40]}' → "
            f"{decision.intent} / {decision.suggested_action} "
            f"(confidence: {decision.confidence:.0%})"
        )

        return decision

    except Exception as e:
        logger.error(f"Classification failed for {email['id'][:8]}: {e}")
        # Safe fallback — if classification fails, mark as FYI and don't act
        return AgentDecision(
            email_id=email["id"],
            intent="fyi",
            suggested_action="mark_read",
            reasoning=f"Classification failed: {str(e)}",
            confidence=0.0,
            requires_approval=False,
        )


def classify_batch(emails: list[dict]) -> list[AgentDecision]:
    """
    Classify a list of emails, returning a decision for each.

    Args:
        emails: List of parsed email dicts.

    Returns:
        List of AgentDecision objects in the same order.
    """
    logger.info(f"Classifying batch of {len(emails)} emails...")
    decisions = []
    for email in emails:
        decision = classify_email(email)
        decisions.append(decision)
    logger.info(f"Batch classification complete: {len(decisions)} decisions")
    return decisions
