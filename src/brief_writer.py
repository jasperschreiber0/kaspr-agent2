"""
brief_writer.py — Write completed trend brief to Supabase trend_briefs table.
"""

import os
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


def write_brief(client_id: str, niche: str, brief: dict) -> dict | None:
    """
    Insert a trend brief row and return the created record.
    """
    row = {
        "client_id": client_id,
        "niche": niche,
        "content_angles": brief.get("content_angles", []),
        "trending_audio": brief.get("trending_audio", []),
        "hashtags": brief.get("hashtags", []),
        "competitor_note": brief.get("competitor_note", ""),
        "raw_brief": brief.get("raw_brief", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        resp = httpx.post(
            f"{SUPABASE_URL}/rest/v1/trend_briefs",
            headers=HEADERS,
            json=row,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        record = data[0] if data else None
        if record:
            print(f"[brief_writer] Wrote brief {record['id']} for client {client_id}")
        return record
    except Exception as e:
        print(f"[brief_writer] Supabase insert failed: {e}")
        return None


def get_active_clients() -> list[dict]:
    """
    Fetch all active clients from Supabase.
    """
    try:
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/clients",
            headers=HEADERS,
            params={"active": "eq.true", "select": "id,business_name,niche"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[brief_writer] Failed to fetch clients: {e}")
        return []


def get_previous_brief(client_id: str) -> dict | None:
    """
    Fetch the most recent brief for a client (used as fallback if scraping fails).
    """
    try:
        resp = httpx.get(
            f"{SUPABASE_URL}/rest/v1/trend_briefs",
            headers=HEADERS,
            params={
                "client_id": f"eq.{client_id}",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception as e:
        print(f"[brief_writer] Failed to fetch previous brief: {e}")
        return None
