"""
synthesiser.py — Uses Claude Haiku to turn raw scrape data into
a structured trend brief for Agent 3 (Publisher).
"""

import os
import json
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


SYSTEM_PROMPT = """You are a social media strategist for Australian small businesses.
You write punchy, practical trend briefs that non-marketers can act on immediately.
Always output valid JSON only. No markdown, no preamble, no explanation."""

BRIEF_SCHEMA = """{
  "content_angles": ["angle 1", "angle 2", "angle 3"],
  "trending_audio": ["TikTok audio name 1 by artist", "TikTok audio name 2 by artist"],
  "hashtags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9", "tag10"],
  "competitor_note": "One observation about what competitors are doing this week.",
  "raw_brief": "A 2-3 sentence plain English summary a business owner would actually read."
}"""


def synthesise(niche: str, tiktok_data: list[dict], instagram_data: list[dict]) -> dict | None:
    """
    Send raw scrape data to Claude Haiku and get back a structured trend brief.
    Returns parsed dict or None on failure.
    """

    # Summarise raw data compactly to stay within token budget
    tt_summary = _summarise_tiktok(tiktok_data)
    ig_summary = _summarise_instagram(instagram_data)

    user_prompt = f"""Niche: {niche}

TikTok top content this week:
{tt_summary}

Instagram top content this week:
{ig_summary}

Write a trend brief for an Australian {niche.replace("_", " ")} business.
Return ONLY a JSON object matching this schema exactly:
{BRIEF_SCHEMA}"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = message.content[0].text.strip()

        # Strip any accidental markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        brief = json.loads(raw)

        # Validate required keys
        required = ["content_angles", "trending_audio", "hashtags", "competitor_note", "raw_brief"]
        for key in required:
            if key not in brief:
                print(f"[synthesiser] Missing key in brief: {key}")
                return None

        return brief

    except json.JSONDecodeError as e:
        print(f"[synthesiser] JSON parse failed: {e}")
        return None
    except Exception as e:
        print(f"[synthesiser] Claude API error: {e}")
        return None


def _summarise_tiktok(data: list[dict]) -> str:
    if not data:
        return "No TikTok data available."

    lines = []
    for i, v in enumerate(data[:5], 1):
        audio = f"{v['music_name']} by {v['music_author']}" if v.get("music_name") else "unknown"
        tags = ", ".join(f"#{t}" for t in (v.get("hashtags") or [])[:5])
        lines.append(
            f"{i}. Plays:{v.get('plays',0):,} Likes:{v.get('likes',0):,} | "
            f"Audio: {audio} | Tags: {tags} | Text: {v.get('text','')[:100]}"
        )
    return "\n".join(lines)


def _summarise_instagram(data: list[dict]) -> str:
    if not data:
        return "No Instagram data available."

    lines = []
    for i, p in enumerate(data[:5], 1):
        tags = ", ".join(f"#{t}" for t in (p.get("hashtags") or [])[:5])
        lines.append(
            f"{i}. Likes:{p.get('likes',0):,} | Type:{p.get('type','image')} | "
            f"Tags: {tags} | Caption: {p.get('caption','')[:100]}"
        )
    return "\n".join(lines)
