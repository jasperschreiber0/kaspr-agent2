"""
trend_runner.py — Main orchestrator for kaspr-agent2 (Trend Scout).

Flow:
  1. Load active clients from Supabase
  2. For each client: scrape TikTok + Instagram → synthesise brief → write to DB
  3. Emit OpenClaw event: trend.brief.ready
  4. Notify Discord #kaspr-logs
  5. Update OpenClaw agent status

OpenClaw awareness:
  - Reads from: clients table
  - Writes to:  trend_briefs table, openclaw_events table, openclaw_agent_status table
  - Emits:      trend.brief.ready
  - Listens to: (none — cron driven, but respects trend.scan.requested event)
"""

import os
import time
from datetime import datetime, timezone

from src.scrapers import scrape_tiktok, scrape_instagram
from src.synthesiser import synthesise
from src.brief_writer import write_brief, get_active_clients, get_previous_brief
from src import openclaw, discord


def run_for_client(client: dict) -> bool:
    """
    Run the full trend scan pipeline for a single client.
    Returns True on success, False on failure.
    """
    client_id = client["id"]
    business_name = client["business_name"]
    niche = client["niche"]

    print(f"\n[trend_runner] Processing client: {business_name} | niche: {niche}")
    openclaw.log_soul_status("running", f"Scanning trends for {business_name}")

    # 1. Scrape TikTok
    print(f"[trend_runner] Scraping TikTok for niche: {niche}")
    tiktok_data = scrape_tiktok(niche)
    print(f"[trend_runner] TikTok results: {len(tiktok_data)} items")

    # Small delay between API calls to be polite
    time.sleep(3)

    # 2. Scrape Instagram
    print(f"[trend_runner] Scraping Instagram for niche: {niche}")
    instagram_data = scrape_instagram(niche)
    print(f"[trend_runner] Instagram results: {len(instagram_data)} items")

    # 3. Check if we have enough data to synthesise
    if not tiktok_data and not instagram_data:
        print(f"[trend_runner] No scrape data for {business_name} — using previous brief")
        discord.error(
            title="Trend Scout — No Scrape Data",
            detail=f"Both TikTok and Instagram returned nothing for {business_name} ({niche}). Using previous brief.",
            client_id=client_id,
        )
        # Fallback: re-use previous brief (Agent 3 will still get the event)
        prev = get_previous_brief(client_id)
        if prev:
            openclaw.emit("trend.brief.ready", {
                "client_id": client_id,
                "brief_id": prev["id"],
                "business_name": business_name,
                "niche": niche,
                "fallback": True,
            })
            return True
        return False

    # 4. Synthesise brief with Claude Haiku
    print(f"[trend_runner] Synthesising brief for {business_name}...")
    brief = synthesise(niche, tiktok_data, instagram_data)

    if not brief:
        print(f"[trend_runner] Synthesis failed for {business_name}")
        discord.error(
            title="Trend Scout — Synthesis Failed",
            detail=f"Claude Haiku failed to produce a valid brief for {business_name}.",
            client_id=client_id,
        )
        return False

    # 5. Write to Supabase
    record = write_brief(client_id, niche, brief)
    if not record:
        print(f"[trend_runner] DB write failed for {business_name}")
        discord.error(
            title="Trend Scout — DB Write Failed",
            detail=f"Could not write trend brief to Supabase for {business_name}.",
            client_id=client_id,
        )
        return False

    brief_id = record["id"]
    print(f"[trend_runner] ✅ Brief written: {brief_id}")

    # 6. Emit OpenClaw event → Agent 3 (Publisher) picks this up
    openclaw.emit("trend.brief.ready", {
        "client_id": client_id,
        "brief_id": brief_id,
        "business_name": business_name,
        "niche": niche,
        "content_angles": brief.get("content_angles", []),
        "fallback": False,
    })

    # 7. Notify Discord
    discord.brief_ready(client_id, business_name, niche, brief_id)

    return True


def run_all() -> None:
    """
    Main entry point: run trend scan for all active clients.
    Called by Railway cron at 7:00am AEST daily.
    Also callable on-demand via OpenClaw event.
    """
    start = datetime.now(timezone.utc)
    print(f"\n{'='*60}")
    print(f"[trend_runner] Kaspr Trend Scout starting at {start.isoformat()}")
    print(f"{'='*60}")

    openclaw.log_soul_status("running", "Daily trend scan started")

    # Load active clients
    clients = get_active_clients()
    if not clients:
        print("[trend_runner] No active clients found. Exiting.")
        openclaw.log_soul_status("idle", "No active clients")
        return

    print(f"[trend_runner] Found {len(clients)} active client(s)")

    successes = 0
    failures = 0

    for client in clients:
        try:
            ok = run_for_client(client)
            if ok:
                successes += 1
            else:
                failures += 1
            # Pause between clients to respect API rate limits
            time.sleep(5)
        except Exception as e:
            failures += 1
            print(f"[trend_runner] Unhandled error for client {client.get('id')}: {e}")
            discord.error(
                title="Trend Scout — Unhandled Error",
                detail=str(e),
                client_id=client.get("id", "unknown"),
            )

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    summary = f"Done in {elapsed:.1f}s | ✅ {successes} succeeded | ❌ {failures} failed"
    print(f"\n[trend_runner] {summary}")

    openclaw.log_soul_status(
        "idle" if failures == 0 else "error",
        summary,
    )

    # Final Discord summary
    discord.log(
        title="📊 Trend Scout Run Complete",
        fields=[
            {"name": "Clients processed", "value": str(len(clients)), "inline": True},
            {"name": "Successes", "value": str(successes), "inline": True},
            {"name": "Failures", "value": str(failures), "inline": True},
            {"name": "Duration", "value": f"{elapsed:.1f}s", "inline": True},
        ],
        color=0x4ade80 if failures == 0 else 0xf59e0b,
    )
