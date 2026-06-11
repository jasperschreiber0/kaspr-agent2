"""
discord.py — Discord webhook helpers for kaspr-agent2.
"""

import os
import httpx
from datetime import datetime, timezone

LOGS_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_KASPR_LOGS")
ERRORS_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_KASPR_ERRORS")


def _post(webhook_url: str, payload: dict) -> None:
    if not webhook_url:
        return
    try:
        httpx.post(webhook_url, json=payload, timeout=8)
    except Exception as e:
        print(f"[discord] Webhook post failed: {e}")


def log(title: str, fields: list[dict], color: int = 0x4ade80) -> None:
    _post(LOGS_WEBHOOK, {
        "embeds": [{
            "title": title,
            "color": color,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    })


def error(title: str, detail: str, client_id: str = "unknown") -> None:
    # Discord rejects empty field values and values over 1024 chars,
    # and _post swallows the 4xx — sanitize so error alerts always land.
    detail = (detail or "(no detail)")[:1000]
    _post(ERRORS_WEBHOOK, {
        "embeds": [{
            "title": f"🚨 {title}",
            "color": 0xef4444,
            "fields": [
                {"name": "Detail", "value": detail, "inline": False},
                {"name": "Agent", "value": "kaspr-trend-scout", "inline": True},
                {"name": "Client ID", "value": client_id, "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]
    })


def brief_ready(client_id: str, business_name: str, niche: str, brief_id: str) -> None:
    log(
        title="📊 Trend Brief Ready",
        fields=[
            {"name": "Business", "value": business_name, "inline": True},
            {"name": "Niche", "value": niche, "inline": True},
            {"name": "Brief ID", "value": brief_id, "inline": False},
            {"name": "Client ID", "value": client_id, "inline": True},
        ],
        color=0x818cf8,
    )
