"""
api/app.py

FastAPI application — the agent's HTTP interface.

This turns the orchestrator from a CLI script into a deployable service.
Every agent capability is now accessible via HTTP, which means:
  - n8n can trigger runs via webhook (POST /run)
  - A frontend can show the approval queue (GET /pending)
  - Any HTTP client can approve/reject actions (POST /approve, /reject)
  - Railway can health-check the service (GET /health)

Key concept: BACKGROUND TASKS
The /run endpoint uses FastAPI's BackgroundTasks so the HTTP response
returns immediately ("run started") while the agent works in the background.
This prevents HTTP timeouts on large inboxes.
"""

import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from orchestrator import run_agent
from agent.router import get_pending_approvals, approve_action, reject_action
from auth.gmail_auth import get_calendar_service
from api.models import (
    RunRequest,
    RunResponse,
    RunResult,
    DecisionSummary,
    PendingResponse,
    ActionResponse,
    HealthResponse,
    ApproveRequest,
    CalendarEvent,
    CalendarEventsResponse,
)
from utils.logger import logger

# ── App setup ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Email & Calendar Automation Agent",
    description=(
        "An agentic AI system that automates email sorting, "
        "smart replies, and meeting scheduling using Gmail API and GPT-4o."
    ),
    version="0.2.0",
    docs_url="/docs",       # Swagger UI at /docs
    redoc_url="/redoc",     # ReDoc at /redoc
)

# Allow all origins for local dev — tighten this in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory run history — stores results of recent /run calls
_run_history: list[dict] = []


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """
    Health check endpoint.
    Railway and other deployment platforms ping this to verify the service is up.
    """
    return HealthResponse(
        status="healthy",
        version="0.2.0",
        phase="Phase 3 — FastAPI + ngrok",
    )


@app.post("/run", tags=["Agent"])
async def trigger_run(
    request: RunRequest,
    background_tasks: BackgroundTasks,
):
    """
    Trigger an agent run in the background.

    Fetches emails, classifies them with GPT-4o, and routes each decision.
    Returns immediately — check /pending for queued approval items.

    - **max_emails**: How many emails to process (1-50)
    - **unread_only**: If true, only processes unread emails
    """
    logger.info(
        f"POST /run — max_emails={request.max_emails}, "
        f"unread_only={request.unread_only}"
    )

    # Run the agent in the background so HTTP returns immediately
    background_tasks.add_task(
        _run_and_store,
        request.max_emails,
        request.unread_only,
    )

    return {
        "status": "started",
        "message": f"Agent run started. Processing up to {request.max_emails} emails.",
        "check": "GET /pending to see actions queued for approval",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/run/sync", tags=["Agent"])
async def trigger_run_sync(request: RunRequest):
    """
    Trigger an agent run synchronously and return full results.
    Use this for testing — for production use POST /run (background).
    """
    logger.info(f"POST /run/sync — max_emails={request.max_emails}")

    results = run_agent(
        max_emails=request.max_emails,
        unread_only=request.unread_only,
    )

    if not results:
        return {
            "status": "complete",
            "emails_processed": 0,
            "message": "No emails found to process.",
        }

    auto_executed = sum(1 for r in results if r["result"].get("status") == "executed")
    queued = sum(1 for r in results if r["result"].get("status") == "queued")

    return {
        "status": "complete",
        "emails_processed": len(results),
        "auto_executed": auto_executed,
        "queued_for_approval": queued,
        "results": results,
    }


@app.get("/pending", response_model=PendingResponse, tags=["Approvals"])
async def get_pending():
    """
    Get all agent actions currently waiting for human approval.

    These are actions the agent wants to take but won't execute
    until you approve them via POST /approve/{email_id}.
    """
    pending = get_pending_approvals()
    only_pending = [p for p in pending if p.get("status") == "pending"]

    logger.info(f"GET /pending — {len(only_pending)} items waiting")

    return PendingResponse(
        count=len(only_pending),
        items=only_pending,
    )


@app.post("/approve/{email_id}", response_model=ActionResponse, tags=["Approvals"])
async def approve(email_id: str, request: ApproveRequest = ApproveRequest()):
    """
    Approve a queued agent action.

    This marks the action as approved. In Phase 4, approval immediately
    triggers the Gmail send or Calendar booking API call.

    - **email_id**: The Gmail message ID (from GET /pending)
    """
    logger.info(f"POST /approve/{email_id}")
    result = approve_action(email_id)

    if result["status"] == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"No pending action found for email_id: {email_id}",
        )

    return ActionResponse(
        status="approved",
        email_id=email_id,
        message=f"Action approved. Phase 4 will execute the Gmail/Calendar API call.",
    )


@app.post("/reject/{email_id}", response_model=ActionResponse, tags=["Approvals"])
async def reject(email_id: str):
    """
    Reject a queued agent action.

    The action will be discarded — no email sent, no meeting booked.

    - **email_id**: The Gmail message ID (from GET /pending)
    """
    logger.info(f"POST /reject/{email_id}")
    result = reject_action(email_id)

    if result["status"] == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"No pending action found for email_id: {email_id}",
        )

    return ActionResponse(
        status="rejected",
        email_id=email_id,
        message="Action rejected. No further processing.",
    )


@app.get("/calendar/events", response_model=CalendarEventsResponse, tags=["Calendar"])
async def get_calendar_events(
    days_ahead: int = Query(default=7, ge=1, le=90, description="How many days ahead to fetch"),
    max_results: int = Query(default=20, ge=1, le=100, description="Maximum number of events to return"),
):
    """
    Fetch upcoming events from the primary Google Calendar.

    - **days_ahead**: Window size in days from now (1–90, default 7)
    - **max_results**: Cap on events returned (1–100, default 20)
    """
    try:
        service = get_calendar_service()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Calendar auth failed: {e}")

    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    try:
        result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except Exception as e:
        logger.error(f"Google Calendar API error: {e}")
        raise HTTPException(status_code=502, detail=f"Google Calendar API error: {e}")

    raw_events = result.get("items", [])

    events: list[CalendarEvent] = []
    for ev in raw_events:
        start_raw = ev.get("start", {})
        end_raw = ev.get("end", {})
        all_day = "date" in start_raw and "dateTime" not in start_raw

        meet_link = ""
        conf = ev.get("conferenceData", {})
        for ep in conf.get("entryPoints", []):
            if ep.get("entryPointType") == "video":
                meet_link = ep.get("uri", "")
                break

        events.append(
            CalendarEvent(
                id=ev["id"],
                title=ev.get("summary", "(no title)"),
                start=start_raw.get("dateTime") or start_raw.get("date", ""),
                end=end_raw.get("dateTime") or end_raw.get("date", ""),
                all_day=all_day,
                attendees=[a["email"] for a in ev.get("attendees", [])],
                calendar_link=ev.get("htmlLink"),
                meet_link=meet_link or None,
                status=ev.get("status", "confirmed"),
            )
        )

    logger.info(f"GET /calendar/events — {len(events)} events in next {days_ahead} days")
    return CalendarEventsResponse(
        count=len(events),
        time_min=time_min,
        time_max=time_max,
        events=events,
    )


@app.get("/history", tags=["Agent"])
async def get_history():
    """
    Get results from recent agent runs.
    Stored in memory — resets when the server restarts.
    """
    return {
        "runs": len(_run_history),
        "history": _run_history[-10:],  # Last 10 runs
    }


# ── Background task helper ─────────────────────────────────────────────────────

async def _run_and_store(max_emails: int, unread_only: bool):
    """Run the agent and store results in history."""
    try:
        results = run_agent(max_emails=max_emails, unread_only=unread_only)
        if results:
            _run_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "emails_processed": len(results),
                "auto_executed": sum(
                    1 for r in results if r["result"].get("status") == "executed"
                ),
                "queued": sum(
                    1 for r in results if r["result"].get("status") == "queued"
                ),
            })
    except Exception as e:
        logger.error(f"Background run failed: {e}")
