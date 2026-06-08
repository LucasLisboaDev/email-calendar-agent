"""
main.py

Entry point for the Email & Calendar Automation Agent.
Run this to test Phase 1: authenticate with Gmail and fetch recent emails.

Usage:
    python main.py
"""

import json
from dotenv import load_dotenv

load_dotenv()

from ingestion.gmail_reader import fetch_emails
from utils.logger import logger


def run_phase1_test():
    """
    Phase 1 test: authenticate → fetch emails → print parsed output.
    First run will open a browser window for Gmail login.
    """
    logger.info("Starting Email & Calendar Agent — Phase 1 test")
    logger.info("Fetching emails from Gmail...")

    try:
        emails = fetch_emails(max_results=5, unread_only=False)

        if not emails:
            logger.warning("No emails returned. Check your Gmail label and fetch settings.")
            return

        logger.info(f"Successfully fetched {len(emails)} emails\n")

        for i, email in enumerate(emails, 1):
            print(f"\n{'='*60}")
            print(f"Email {i} of {len(emails)}")
            print(f"{'='*60}")
            print(json.dumps(email, indent=2, ensure_ascii=False))

        logger.info("Phase 1 complete. Pipeline is working.")

    except FileNotFoundError as e:
        logger.error(str(e))
        logger.info("Make sure credentials.json is in the project root.")

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")


if __name__ == "__main__":
    run_phase1_test()
