"""
scrapers.py — TikTok and Instagram trend scrapers via Apify.
Returns normalised trend data for the synthesiser.
"""

import os
from apify_client import ApifyClient

client = ApifyClient(os.environ["APIFY_TOKEN"])

# Niche → seed hashtags for each platform
NICHE_HASHTAGS = {
    "beauty_salon":    ["beautysalon", "hairsalon", "hairtransformation", "salonlife", "wollongongbeauty"],
    "nail_studio":     ["nailart", "nailsofinstagram", "nails", "nailtech", "gelmanicure"],
    "pilates_yoga":    ["pilates", "yoga", "reformerpilates", "pilateslife", "yogaaustalia"],
    "allied_health":   ["physio", "occupationaltherapy", "speechtherapy", "alliedhealth", "healthcareau"],
    "cafe_brunch":     ["brunch", "cafe", "coffeetime", "wollongongcafe", "sydneycafe"],
    "boutique_retail": ["boutique", "shoplocal", "smallbusiness", "fashionaustralia", "ootd"],
    "pet_grooming":    ["petgrooming", "dogsofinstagram", "grooming", "doglife", "petcare"],
    "personal_training": ["personaltrainer", "fitness", "gymlife", "fitspo", "australiafitness"],
    "wellness":        ["wellness", "selfcare", "holistichealth", "wellnessaustralia", "mindfulness"],
}

DEFAULT_HASHTAGS = ["smallbusiness", "australia", "localbusiness"]


def get_hashtags(niche: str) -> list[str]:
    return NICHE_HASHTAGS.get(niche, DEFAULT_HASHTAGS)


def scrape_tiktok(niche: str, max_items: int = 10) -> list[dict]:
    """
    Use Apify's TikTok scraper to get top recent videos for niche hashtags.
    Returns list of normalised video dicts.
    """
    hashtags = get_hashtags(niche)
    results = []

    try:
        run = client.actor("clockworks/tiktok-scraper").call(
            run_input={
                "hashtags": hashtags[:3],   # Top 3 to stay within credits
                "resultsPerPage": max_items,
                "maxItems": max_items,
                "shouldDownloadVideos": False,
                "shouldDownloadCovers": False,
            }
        )

        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            results.append({
                "platform": "tiktok",
                "text": item.get("text", "")[:300],
                "likes": item.get("diggCount", 0),
                "comments": item.get("commentCount", 0),
                "shares": item.get("shareCount", 0),
                "plays": item.get("playCount", 0),
                "hashtags": item.get("hashtags", []),
                "music_name": item.get("musicMeta", {}).get("musicName", ""),
                "music_author": item.get("musicMeta", {}).get("musicAuthor", ""),
            })

    except Exception as e:
        print(f"[scrapers] TikTok scrape failed for niche {niche}: {e}")

    return results


def scrape_instagram(niche: str, max_items: int = 9) -> list[dict]:
    """
    Use Apify's Instagram scraper to get top recent posts for niche hashtags.
    Returns list of normalised post dicts.
    """
    hashtags = get_hashtags(niche)
    results = []

    try:
        run = client.actor("apify/instagram-scraper").call(
            run_input={
                "hashtags": hashtags[:3],
                "resultsLimit": max_items,
                "scrapeType": "hashtag",
                "addParentData": False,
            }
        )

        for item in client.dataset(run["defaultDatasetId"]).iterate_items():
            results.append({
                "platform": "instagram",
                "caption": (item.get("caption") or "")[:300],
                "likes": item.get("likesCount", 0),
                "comments": item.get("commentsCount", 0),
                "type": item.get("type", "image"),   # image | video | sidecar
                "hashtags": item.get("hashtags", []),
            })

    except Exception as e:
        print(f"[scrapers] Instagram scrape failed for niche {niche}: {e}")

    return results
