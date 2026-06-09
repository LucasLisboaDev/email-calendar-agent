"""
orchestrator.py

The main agentic loop for Phase 2.

This is the ReAct pattern in action:
  Reason  → classifier.py reads the email and decides what to do
  Act     → router.py dispatches or queues the action
  Observe → we log every step and collect results

Run this instead of main.py from Phase 2 onward.

Usage:
    python orchestrator.py
"""

import json
from dotenv import load_dotenv

load_dotenv()

from ingestion.gmail_reader import fetch_emails
from ingestion.html_cleaner import clean_email_body
from agent.classifier import classify_batch
from agent.router import route, get_pending_approvals
from utils.logger import logger


def run_agent(max_emails: int = 5, unread_only: bool = True):
    """
    Full agentic pipeline: fetch → clean → classify → route.

    Args:
        max_emails: How many emails to process per run.
        unread_only: Only process unread emails.
    """
    logger.info("=" * 60)
    logger.info("Email & Calendar Agent — Phase 2 orchestrator starting")
    logger.info("=" * 60)

    # ── Step 1: Fetch emails ──────────────────────────────────────
    logger.info(f"Fetching up to {max_emails} emails...")
    emails = fetch_emails(max_results=max_emails, unread_only=unread_only)

    if not emails:
        logger.warning("No emails to process. Exiting.")
        return

    logger.info(f"Fetched {len(emails)} emails")

    # ── Step 2: Clean bodies ──────────────────────────────────────
    logger.info("Cleaning email bodies...")
    for email in emails:
        original_len = len(email.get("body", ""))
        email["body"] = clean_email_body(email.get("body", ""))
        cleaned_len = len(email["body"])
        if original_len > 0:
            reduction = (1 - cleaned_len / original_len) * 100
            logger.debug(
                f"[{email['id'][:8]}] Body cleaned: "
                f"{original_len} → {cleaned_len} chars ({reduction:.0f}% reduction)"
            )

    # ── Step 3: Classify all emails ───────────────────────────────
    logger.info("Classifying emails with GPT-4o...")
    decisions = classify_batch(emails)

    # ── Step 4: Route each decision ───────────────────────────────
    logger.info("Routing decisions...")
    results = []
    for email, decision in zip(emails, decisions):
        result = route(email, decision)
        results.append({
            "email": {
                "id": email["id"],
                "from": email.get("from", ""),
                "subject": email.get("subject", ""),
            },
            "decision": {
                "intent": decision.intent,
                "action": decision.suggested_action,
                "confidence": decision.confidence,
                "reasoning": decision.reasoning,
            },
            "result": result,
        })

    # ── Step 5: Print summary ─────────────────────────────────────
    _print_summary(results)

    # ── Step 6: Show approval queue ───────────────────────────────
    pending = get_pending_approvals()
    if pending:
        _print_approval_queue(pending)

    logger.info("Orchestrator run complete.")
    return results


def _print_summary(results: list[dict]):
    """Print a clean run summary to the terminal."""
    print("\n" + "=" * 60)
    print("AGENT RUN SUMMARY")
    print("=" * 60)

    for i, r in enumerate(results, 1):
        email = r["email"]
        decision = r["decision"]
        result = r["result"]

        status_icon = {
            "executed": "✅",
            "queued": "⏳",
            "error": "❌",
        }.get(result.get("status", ""), "•")

        print(f"\n{i}. {status_icon} [{email['id'][:8]}]")
        print(f"   From:    {email['from'][:50]}")
        print(f"   Subject: {email['subject'][:50]}")
        print(f"   Intent:  {decision['intent']}")
        print(f"   Action:  {decision['action']} ({decision['confidence']:.0%} confidence)")
        print(f"   Reason:  {decision['reasoning'][:80]}")
        print(f"   Status:  {result.get('message', result.get('status', ''))}")

    # Tally
    executed = sum(1 for r in results if r["result"].get("status") == "executed")
    queued = sum(1 for r in results if r["result"].get("status") == "queued")

    print(f"\n{'─'*60}")
    print(f"Total: {len(results)} emails | Auto-executed: {executed} | Queued for approval: {queued}")
    print("=" * 60 + "\n")


def _print_approval_queue(pending: list[dict]):
    """Print all actions waiting for human approval."""
    print("\n" + "=" * 60)
    print("⏳ PENDING HUMAN APPROVAL")
    print("=" * 60)

    for i, item in enumerate(pending, 1):
        print(f"\n{i}. [{item['email_id'][:8]}] {item['subject'][:50]}")
        print(f"   From:   {item['from'][:50]}")
        print(f"   Action: {item['suggested_action']}")
        print(f"   Reason: {item['reasoning'][:80]}")

        if item.get("draft_reply"):
            print(f"\n   Draft reply:")
            print(f"   {'─'*40}")
            for line in item["draft_reply"].split("\n"):
                print(f"   {line}")
            print(f"   {'─'*40}")

        if item.get("meeting_details"):
            details = item["meeting_details"]
            print(f"\n   Meeting details:")
            print(f"   Time:     {details.get('proposed_time', 'TBD')}")
            print(f"   Duration: {details.get('duration_minutes', '?')} min")
            print(f"   Topic:    {details.get('topic', 'TBD')}")

    print("\n" + "=" * 60)
    print("Phase 4 will add approve/reject via FastAPI endpoints.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_agent(max_emails=5, unread_only=False)
