"""
openclaw.py — OpenClaw event bus integration for kaspr-agent2.

OpenClaw is a lightweight polling queue built on two Postgres tables,
NOT Supabase Realtime — despite this module's name, nothing here uses a
Realtime subscription. Agents emit events by inserting rows into the
`openclaw_events` table; other agents notice them by polling on an
interval (agent2: every 60s in daemon mode; agent3: every 30s). If you
need sub-poll-interval latency, this isn't that yet.

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
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
    "SUPABASE_SERVICE_KEY"
)

HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
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
    Note: as of this audit, nothing in kaspr-site/agent1/agent2/agent3
    reads this table back — it's write-only from this system's
    perspective. Kept in case an external OpenClaw dashboard reads it;
    worth removing if that turns out not to exist.
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
