"""
api/models.py

Pydantic models for all FastAPI request and response bodies.

Why separate models from utils/email_models.py?
- email_models.py defines the internal data contract (agent ↔ agent)
- api/models.py defines the external API contract (client ↔ server)
- Keeps the API surface clean and versioned independently of internals
"""

from typing import Optional
from pydantic import BaseModel, Field


# ── Request models ─────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    """Body for POST /run — trigger an agent run."""
    max_emails: int = Field(default=5, ge=1, le=50, description="Number of emails to process")
    unread_only: bool = Field(default=True, description="Only process unread emails")


class ApproveRequest(BaseModel):
    """Optional body for POST /approve/{email_id}."""
    notes: Optional[str] = Field(default=None, description="Optional reviewer notes")


# ── Response models ────────────────────────────────────────────────────────────

class EmailSummary(BaseModel):
    """Minimal email info included in API responses."""
    id: str
    from_: str = Field(alias="from")
    subject: str

    model_config = {"populate_by_name": True}


class DecisionSummary(BaseModel):
    """Agent decision info included in API responses."""
    intent: str
    suggested_action: str
    confidence: float
    reasoning: str
    requires_approval: bool
    draft_reply: Optional[str] = None
    meeting_details: Optional[dict] = None


class RunResult(BaseModel):
    """Single email result from a /run response."""
    email: dict
    decision: DecisionSummary
    result: dict


class RunResponse(BaseModel):
    """Response body for POST /run."""
    status: str
    emails_processed: int
    auto_executed: int
    queued_for_approval: int
    results: list[RunResult]


class PendingItem(BaseModel):
    """Single item in the approval queue."""
    email_id: str
    from_: str = Field(alias="from")
    subject: str
    intent: str
    suggested_action: str
    reasoning: str
    confidence: float
    status: str
    draft_reply: Optional[str] = None
    meeting_details: Optional[dict] = None

    model_config = {"populate_by_name": True}


class PendingResponse(BaseModel):
    """Response body for GET /pending."""
    count: int
    items: list[dict]


class ActionResponse(BaseModel):
    """Response body for approve/reject endpoints."""
    status: str
    email_id: str
    message: str


class HealthResponse(BaseModel):
    """Response body for GET /health."""
    status: str
    version: str
    phase: str


class CalendarEvent(BaseModel):
    """A single Google Calendar event."""
    id: str
    title: str
    start: str
    end: str
    all_day: bool
    attendees: list[str]
    calendar_link: Optional[str] = None
    meet_link: Optional[str] = None
    status: str


class CalendarEventsResponse(BaseModel):
    """Response body for GET /calendar/events."""
    count: int
    time_min: str
    time_max: str
    events: list[CalendarEvent]
