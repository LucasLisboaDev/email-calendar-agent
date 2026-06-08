"""
utils/email_models.py

Pydantic models for type-safe email data throughout the pipeline.
Every email that passes through the agent is validated against EmailMessage.

Why Pydantic here?
- Catches malformed API responses early (fail fast)
- Auto-documents the data contract between modules
- Makes IDE autocomplete work properly across the codebase
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class EmailMessage(BaseModel):
    """
    Represents a parsed Gmail message.
    This is the core data type that flows through the entire agent pipeline.
    """

    id: str = Field(..., description="Gmail message ID")
    thread_id: str = Field(..., description="Gmail thread ID")
    from_: str = Field(..., alias="from", description="Sender email address")
    to: str = Field(default="", description="Recipient email address")
    subject: str = Field(default="(no subject)", description="Email subject line")
    body: str = Field(default="", description="Plain text email body")
    timestamp: str = Field(default="", description="ISO 8601 timestamp")
    labels: list[str] = Field(default_factory=list, description="Gmail label IDs")
    snippet: str = Field(default="", description="Gmail preview snippet")

    model_config = {"populate_by_name": True}

    def is_unread(self) -> bool:
        return "UNREAD" in self.labels

    def is_in_inbox(self) -> bool:
        return "INBOX" in self.labels

    def short_preview(self) -> str:
        """Returns a short string for logging/debugging."""
        return f"[{self.id[:8]}] From: {self.from_} | Subject: {self.subject[:50]}"


class AgentDecision(BaseModel):
    """
    Represents the AI agent's classification and intended action for an email.
    Output of Phase 3 (AI reasoning), input to Phase 4 (actions).
    """

    email_id: str
    intent: str = Field(
        ...,
        description="Classified intent: 'meeting_request', 'reply_needed', 'spam', 'fyi', 'urgent'"
    )
    suggested_action: str = Field(
        ...,
        description="What the agent wants to do: 'schedule_meeting', 'draft_reply', 'archive', 'flag'"
    )
    draft_reply: Optional[str] = Field(
        default=None,
        description="Draft reply text if action is draft_reply"
    )
    meeting_details: Optional[dict] = Field(
        default=None,
        description="Parsed meeting details if action is schedule_meeting"
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Agent confidence score 0.0 to 1.0"
    )
    requires_approval: bool = Field(
        default=True,
        description="Whether human approval is needed before executing"
    )
    reasoning: str = Field(
        default="",
        description="Agent's explanation of its decision"
    )
