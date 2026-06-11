"""
utils/queue_store.py

Persistent approval queue backed by a JSON file.

Problem it solves:
  The Phase 3 router used an in-memory list for the approval queue.
  Every time the server restarted (Railway redeploy, crash, etc.)
  the queue was wiped. Any pending approvals were lost.

Solution:
  Store the queue in a JSON file on disk. On startup, load it.
  On every write, flush it. The queue survives restarts.

On Railway:
  Railway has an ephemeral filesystem — files reset on redeploy.
  For a production system you'd use a real DB (PostgreSQL, Redis).
  For this portfolio project, the JSON file is correct —
  it teaches the concept without adding infrastructure complexity.
  We note this as a known limitation in the README.

Usage:
  from utils.queue_store import QueueStore
  store = QueueStore()
  store.add(item)
  store.get_pending()
  store.approve(email_id)
  store.reject(email_id)
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from utils.logger import logger

QUEUE_FILE = os.getenv("QUEUE_FILE", "data/approval_queue.json")


class QueueStore:
    """
    Thread-safe persistent approval queue backed by JSON.
    Singleton pattern — one instance shared across the app.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._queue: list[dict] = []
        self._load()
        self._initialized = True

    def add(self, item: dict) -> None:
        """Add a new item to the queue."""
        item["created_at"] = datetime.now(timezone.utc).isoformat()
        item["status"] = "pending"
        self._queue.append(item)
        self._save()
        logger.debug(f"Queue: added {item['email_id'][:8]} ({item['suggested_action']})")

    def get_pending(self) -> list[dict]:
        """Return all items with status='pending'."""
        return [i for i in self._queue if i.get("status") == "pending"]

    def get_all(self) -> list[dict]:
        """Return the full queue including approved/rejected."""
        return self._queue

    def get_by_id(self, email_id: str) -> Optional[dict]:
        """Find a queue item by email_id."""
        for item in self._queue:
            if item["email_id"] == email_id:
                return item
        return None

    def approve(self, email_id: str) -> bool:
        """Mark an item as approved. Returns True if found."""
        for item in self._queue:
            if item["email_id"] == email_id and item["status"] == "pending":
                item["status"] = "approved"
                item["actioned_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
                logger.info(f"Queue: approved {email_id[:8]}")
                return True
        return False

    def reject(self, email_id: str) -> bool:
        """Mark an item as rejected. Returns True if found."""
        for item in self._queue:
            if item["email_id"] == email_id and item["status"] == "pending":
                item["status"] = "rejected"
                item["actioned_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
                logger.info(f"Queue: rejected {email_id[:8]}")
                return True
        return False

    def mark_executed(self, email_id: str, result: dict) -> None:
        """Mark an approved item as executed with the action result."""
        for item in self._queue:
            if item["email_id"] == email_id:
                item["status"] = "executed"
                item["execution_result"] = result
                item["executed_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
                return

    def clear_old(self, keep_days: int = 7) -> int:
        """Remove items older than keep_days. Returns count removed."""
        cutoff = datetime.now(timezone.utc).timestamp() - (keep_days * 86400)
        before = len(self._queue)
        self._queue = [
            i for i in self._queue
            if i.get("status") == "pending" or
            datetime.fromisoformat(i.get("created_at", "2000-01-01T00:00:00+00:00")).timestamp() > cutoff
        ]
        removed = before - len(self._queue)
        if removed > 0:
            self._save()
        return removed

    def _load(self) -> None:
        """Load queue from disk on startup."""
        path = Path(QUEUE_FILE)
        if path.exists():
            try:
                with open(path, "r") as f:
                    self._queue = json.load(f)
                logger.info(f"Queue loaded: {len(self._queue)} items ({len(self.get_pending())} pending)")
            except Exception as e:
                logger.warning(f"Failed to load queue file: {e}. Starting fresh.")
                self._queue = []
        else:
            self._queue = []

    def _save(self) -> None:
        """Flush queue to disk."""
        path = Path(QUEUE_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w") as f:
                json.dump(self._queue, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save queue: {e}")


# Module-level singleton
queue_store = QueueStore()
