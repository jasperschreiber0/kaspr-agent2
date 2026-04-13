"""
openclaw.py — OpenClaw event bus integration for kaspr-agent2.

OpenClaw uses Supabase Realtime as its event bus.
Agents emit events by inserting rows into the `openclaw_events` table.
Other agents listen via Supabase Realtime subscriptions.

Event schema:
  id:          uuid (auto)
  event_name:  text  e.g. "trend.brief.ready"
  source:      text  e.g. "kaspr-trend-scout"
  payload:     jsonb
  created_at:  timestamptz
"""

import os
import json
import httpx
from datetime import datetime, timezone


SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def emit(event_name: str, payload: dict, source: str = "kaspr-trend-scout") -> dict | None:
    """
    Emit an event to the OpenClaw event bus.
    Inserts a row into openclaw_events table.
    Agent 3 (Publisher) listens for 'trend.brief.ready'.
    """
    row = {
        "event_name": event_name,
        "source": source,
        "payload": payload,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        resp = httpx.post(
            f"{SUPABASE_URL}/rest/v1/openclaw_events",
            headers=HEADERS,
            json=row,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"[openclaw] Emitted: {event_name} | id: {data[0].get('id') if data else 'unknown'}")
        return data[0] if data else None
    except Exception as e:
        print(f"[openclaw] Emit failed for {event_name}: {e}")
        return None


def log_soul_status(status: str, detail: str = "") -> None:
    """
    Log agent health/status to openclaw_agent_status table.
    OpenClaw dashboard reads this to show agent health.
    """
    row = {
        "agent": "kaspr-trend-scout",
        "status": status,          # "running" | "idle" | "error" | "complete"
        "detail": detail,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        # Upsert on agent name so there's always one current row per agent
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/openclaw_agent_status",
            headers={**HEADERS, "Prefer": "resolution=merge-duplicates"},
            json=row,
            timeout=10,
        )
    except Exception as e:
        print(f"[openclaw] Status log failed: {e}")
