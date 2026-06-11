"""
actions/calendar_actions.py

Google Calendar API integration — creates real calendar events.

Key challenge: the agent extracts meeting times as natural language
("Thursday at 3pm", "tomorrow at 2", "next Monday morning").
We need to convert those into proper ISO 8601 datetimes that the
Calendar API accepts.

We solve this with a second GPT-4o call — we ask the model to convert
the natural language time into a structured datetime object. This is
called "LLM-assisted parsing" and is a common pattern in agentic systems
where user/email input is inherently fuzzy.
"""

import os
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from auth.gmail_auth import get_calendar_service
from utils.logger import logger

# Default timezone — matches your location in Frisco, TX
DEFAULT_TIMEZONE = os.getenv("AGENT_TIMEZONE", "America/Chicago")
DEFAULT_DURATION_MINUTES = 30


def create_meeting(
    meeting_details: dict,
    organizer_email: str,
    attendee_email: str,
) -> dict:
    """
    Create a Google Calendar event from extracted meeting details.

    Args:
        meeting_details: Dict from classifier with proposed_time, topic, etc.
        organizer_email: Your Gmail address (the calendar owner).
        attendee_email: The person who requested the meeting.

    Returns:
        Dict with status, event ID, and calendar link.
    """
    try:
        service = get_calendar_service()

        # Parse the natural language time into a real datetime
        proposed_time = meeting_details.get("proposed_time", "")
        duration = meeting_details.get("duration_minutes", DEFAULT_DURATION_MINUTES)
        topic = meeting_details.get("topic", "Meeting")

        start_dt = _parse_meeting_time(proposed_time)
        end_dt = start_dt + timedelta(minutes=duration or DEFAULT_DURATION_MINUTES)

        # Format for Google Calendar API (ISO 8601 with timezone)
        tz = ZoneInfo(DEFAULT_TIMEZONE)
        start_str = start_dt.astimezone(tz).isoformat()
        end_str = end_dt.astimezone(tz).isoformat()

        # Build the event body
        event_body = {
            "summary": topic,
            "description": f"Meeting scheduled by Email Agent\nOriginal request from: {attendee_email}",
            "start": {
                "dateTime": start_str,
                "timeZone": DEFAULT_TIMEZONE,
            },
            "end": {
                "dateTime": end_str,
                "timeZone": DEFAULT_TIMEZONE,
            },
            "attendees": [
                {"email": organizer_email},
                {"email": attendee_email},
            ],
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 24 * 60},  # 1 day before
                    {"method": "popup", "minutes": 30},        # 30 min before
                ],
            },
            "conferenceData": {
                "createRequest": {
                    "requestId": f"agent-{int(datetime.now().timestamp())}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

        # Create the event with Google Meet link
        event = (
            service.events()
            .insert(
                calendarId="primary",
                body=event_body,
                conferenceDataVersion=1,
                sendUpdates="all",  # Sends email invites to attendees
            )
            .execute()
        )

        event_link = event.get("htmlLink", "")
        meet_link = ""
        if "conferenceData" in event:
            entry_points = event["conferenceData"].get("entryPoints", [])
            for ep in entry_points:
                if ep.get("entryPointType") == "video":
                    meet_link = ep.get("uri", "")

        logger.info(
            f"Calendar event created: '{topic}' | "
            f"start={start_str} | "
            f"attendees={organizer_email}, {attendee_email} | "
            f"event_id={event['id']}"
        )

        return {
            "status": "created",
            "event_id": event["id"],
            "title": topic,
            "start": start_str,
            "end": end_str,
            "attendees": [organizer_email, attendee_email],
            "calendar_link": event_link,
            "meet_link": meet_link,
        }

    except Exception as e:
        logger.error(f"Failed to create calendar event: {e}")
        return {"status": "error", "error": str(e)}


def _parse_meeting_time(time_str: str) -> datetime:
    """
    Convert natural language time string to a datetime object.

    Uses GPT-4o for fuzzy parsing — handles expressions like:
    "Thursday at 3pm", "tomorrow morning", "next Monday at 2:30"

    Falls back to next business day at 10am if parsing fails.

    Args:
        time_str: Natural language time string from email.

    Returns:
        datetime object in UTC.
    """
    if not time_str:
        return _next_business_day_at(10)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
        now_str = now.strftime("%A, %B %d %Y %H:%M %Z")

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a datetime parser. Convert natural language time "
                        "expressions to ISO 8601 datetime strings. "
                        "Return ONLY the datetime string, nothing else. "
                        f"Current time: {now_str}. "
                        f"Timezone: {DEFAULT_TIMEZONE}. "
                        "If the day is ambiguous (e.g. 'Thursday' with no date), "
                        "use the next upcoming occurrence of that day."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Convert to ISO 8601: '{time_str}'",
                },
            ],
            max_tokens=50,
            temperature=0,
        )

        dt_str = response.choices[0].message.content.strip()
        # Parse the ISO string
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        logger.info(f"Parsed '{time_str}' → {dt.isoformat()}")
        return dt

    except Exception as e:
        logger.warning(f"Time parsing failed for '{time_str}': {e}. Using fallback.")
        return _next_business_day_at(10)


def _next_business_day_at(hour: int) -> datetime:
    """Return the next business day (Mon-Fri) at the given hour in local time."""
    tz = ZoneInfo(DEFAULT_TIMEZONE)
    dt = datetime.now(tz) + timedelta(days=1)
    # Skip weekends
    while dt.weekday() >= 5:
        dt += timedelta(days=1)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0)
