import os

os.environ.setdefault("APIFY_TOKEN", "test_token")

from src.scrapers import get_hashtags, NICHE_HASHTAGS, DEFAULT_HASHTAGS


def test_known_niche_returns_configured_hashtags():
    assert get_hashtags("nail_studio") == NICHE_HASHTAGS["nail_studio"]


def test_unknown_niche_falls_back_to_default():
    assert get_hashtags("something_made_up") == DEFAULT_HASHTAGS


def test_niches_match_agent3_and_kaspr_site_new_client_form():
    # scheduler.js (agent3) and app/dashboard/new-client/page.tsx
    # (kaspr-site) both hardcode this same niche list. If one repo's
    # list ever changes without the others, a client can be created
    # with a niche that schedules fine but scrapes generically (or vice
    # versa), with nothing anywhere flagging the mismatch.
    expected_niches = {
        "beauty_salon",
        "nail_studio",
        "pilates_yoga",
        "allied_health",
        "cafe_brunch",
        "boutique_retail",
        "pet_grooming",
        "personal_training",
        "wellness",
    }
    assert set(NICHE_HASHTAGS.keys()) == expected_niches
