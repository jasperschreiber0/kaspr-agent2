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
from dotenv import load_dotenv

load_dotenv()

# Validate env
REQUIRED_ENV = [
    "ANTHROPIC_API_KEY",
    "APIFY_TOKEN",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
]

missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
if missing:
    print(f"[cron] ❌ Missing required env vars: {', '.join(missing)}")
    sys.exit(1)

from src.trend_runner import run_all
from src import openclaw

MODE = os.environ.get("MODE", "cron").lower()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]
HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
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


def mark_event_processed(event_id: str) -> None:
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/openclaw_events",
            headers={**HEADERS, "Content-Type": "application/json"},
            params={"id": f"eq.{event_id}"},
            json={"processed": True, "processed_at": datetime.now(timezone.utc).isoformat()},
            timeout=10,
        )
    except Exception as e:
        print(f"[cron] Failed to mark event {event_id} processed: {e}")


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

    while True:
        now = datetime.now(timezone.utc)

        # Daily cron: 7am AEST = 21:00 UTC previous day (or 20:00 during AEDT)
        # Simple approach: run if current hour == 21 and haven't run today
        aest_hour = (now.hour + 10) % 24  # rough AEST offset
        today = now.date()

        if aest_hour == 7 and last_daily_run_date != today:
            print(f"[cron] Daily 7am AEST trigger firing")
            run_all()
            last_daily_run_date = today

        # Check for on-demand events from OpenClaw
        events = poll_openclaw_events()
        for event in events:
            print(f"[cron] On-demand scan requested via OpenClaw event {event['id']}")
            run_all()
            mark_event_processed(event["id"])

        # Poll every 60 seconds
        time.sleep(60)


if __name__ == "__main__":
    if MODE == "daemon":
        run_daemon_mode()
    else:
        run_cron_mode()
