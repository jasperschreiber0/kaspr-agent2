"""
cron.py — Entry point for kaspr-agent2.

Two modes:
  1. CRON mode  — runs once immediately (Railway cron calls this at 7am AEST)
  2. DAEMON mode — stays alive, polls OpenClaw event bus every 60s
                   for on-demand `trend.scan.requested` events

Set MODE=daemon in Railway env vars to run as always-on service.
Default is cron (run once and exit).
"""

import os
import sys
import time
import httpx
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# Validate env
REQUIRED_ENV = [
    "ANTHROPIC_API_KEY",
    "APIFY_TOKEN",
    "SUPABASE_URL",
]

# Standardizing on SUPABASE_SERVICE_ROLE_KEY to match agent1/agent3 — this
# was the only service in the fleet using SUPABASE_SERVICE_KEY for the same
# secret. Fall back to the old name so an already-deployed Railway env
# doesn't break the moment this ships; rename the Railway var when
# convenient and this warning goes away on its own.
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
    "SUPABASE_SERVICE_KEY"
)

missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
if not SUPABASE_SERVICE_ROLE_KEY:
    missing.append("SUPABASE_SERVICE_ROLE_KEY (or legacy SUPABASE_SERVICE_KEY)")
if missing:
    print(f"[cron] ❌ Missing required env vars: {', '.join(missing)}")
    sys.exit(1)

if os.environ.get("SUPABASE_SERVICE_KEY") and not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
    print(
        "[cron] ⚠️  Using legacy SUPABASE_SERVICE_KEY — rename to "
        "SUPABASE_SERVICE_ROLE_KEY in Railway when convenient (matches agent1/agent3)."
    )

from src.trend_runner import run_all
from src import openclaw

MODE = os.environ.get("MODE", "cron").lower()

SUPABASE_URL = os.environ["SUPABASE_URL"]
HEADERS = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
}


def poll_openclaw_events() -> list[dict]:
    """
    Check openclaw_events for unprocessed trend.scan.requested events.
    Returns list of pending event rows.
    """
    try:
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/openclaw_events",
            headers=HEADERS,
            params={
                "event_name": "eq.trend.scan.requested",
                "processed": "eq.false",
                "order": "created_at.asc",
                "limit": "5",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[cron] OpenClaw poll failed: {e}")
        return []


def mark_event_processed(event_id: str) -> bool:
    try:
        resp = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/openclaw_events",
            headers={**HEADERS, "Content-Type": "application/json"},
            params={"id": f"eq.{event_id}"},
            json={"processed": True, "processed_at": datetime.now(timezone.utc).isoformat()},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[cron] Failed to mark event {event_id} processed: {e}")
        return False


def run_cron_mode():
    """Run once and exit — used by Railway cron schedule."""
    print(f"[cron] Mode: CRON | {datetime.now(timezone.utc).isoformat()}")
    run_all()
    print("[cron] Cron run complete. Exiting.")
    sys.exit(0)


def run_daemon_mode():
    """
    Stay alive and poll for on-demand scan requests from OpenClaw.
    Also runs the daily scan at 7am AEST if not already run today.
    """
    print(f"[cron] Mode: DAEMON | Started at {datetime.now(timezone.utc).isoformat()}")
    openclaw.log_soul_status("idle", "Daemon started, polling for events")

    last_daily_run_date = None
    sydney = ZoneInfo("Australia/Sydney")
    # Events we ran but could not mark processed — skip them so a failing
    # PATCH doesn't re-trigger a full (paid) scan every poll cycle.
    unmarkable_event_ids: set[str] = set()

    while True:
        local_now = datetime.now(sydney)
        today = local_now.date()

        if local_now.hour == 7 and last_daily_run_date != today:
            print(f"[cron] Daily 7am Sydney trigger firing")
            run_all()
            last_daily_run_date = today

        # Check for on-demand events from OpenClaw
        events = [e for e in poll_openclaw_events() if e["id"] not in unmarkable_event_ids]
        if events:
            # One scan covers all pending requests — run_all() isn't
            # parameterized per event, so running it N times is pure waste.
            ids = [e["id"] for e in events]
            print(f"[cron] On-demand scan requested via OpenClaw event(s): {', '.join(ids)}")
            run_all()
            for event_id in ids:
                if not mark_event_processed(event_id):
                    unmarkable_event_ids.add(event_id)

        # Poll every 60 seconds
        time.sleep(60)


if __name__ == "__main__":
    if MODE == "daemon":
        run_daemon_mode()
    else:
        run_cron_mode()
