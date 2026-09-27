"""Settings live in the Google Sheet's `Settings` tab so you can edit them from your phone.

Anything missing from the sheet falls back to DEFAULTS below (and `init` writes the
defaults into the sheet the first time). Secrets never go in the sheet; they come from
environment variables (GitHub Actions secrets).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

# key -> (default value, description shown in the sheet)
DEFAULTS: dict[str, tuple[str, str]] = {
    # --- Phase 1: niche -------------------------------------------------------------
    "niche_statement": (
        "AI tools and automation for small business owners",
        "One line: who it's for + what it's about. Used by the AI for every relevance check.",
    ),
    "seed_keywords": (
        "ChatGPT for business, AI automation, WhatsApp chatbot, AI tools, AI for small business, "
        "business automation, AI marketing, no code automation, AI agents, Canva AI",
        "10-15 comma-separated search terms your audience would type.",
    ),
    "adjacent_niches": (
        "entrepreneurship: startup tips, business ideas | productivity: productivity apps, time management | "
        "marketing: instagram marketing, lead generation",
        "Format  name: kw, kw | name: kw. Used for discovery of fresh angles.",
    ),
    "content_language": ("Hindi/Hinglish", "Language of the reels you watch (helps transcription + AI)."),
    # --- Phase 4: outlier rules -------------------------------------------------------
    "outlier_threshold": ("5", "Flag reels with views >= this x the creator's median (drop to 3 for small niches)."),
    "trend_window_days": ("14", "Reels up to this age are tagged 'trend'."),
    "evergreen_window_days": ("180", "Reels up to this age are tagged 'evergreen'; older are ignored."),
    "min_reel_age_hours": ("48", "Don't score reels younger than this (views still climbing)."),
    # --- Phase 3: baselines -------------------------------------------------------------
    "baseline_sample": ("20", "Median is taken over this many most-recent eligible reels."),
    "baseline_min_age_days": ("7", "Only reels at least this old count toward the median."),
    "baseline_min_sample": ("10", "Below this many eligible reels the baseline is marked low confidence."),
    # --- Phase 5: validation --------------------------------------------------------
    "boost_ratio_floor": (
        "0.3",
        "Reject as 'suspect boost' if engagement/views is below this x the creator's usual ratio.",
    ),
    "relevance_min": ("6", "Minimum AI relevance score (0-10) to keep an outlier."),
    "reject_caption_terms": (
        "giveaway, #ad, #sponsored, paid partnership, #collab, contest, #partner",
        "Captions containing any of these are rejected as not-real.",
    ),
    # --- Phase 2 / 9: watch list ---------------------------------------------------------
    "target_big": ("5", "Target number of big accounts (500K+)."),
    "target_mid": ("10", "Target number of mid accounts (50K-500K)."),
    "target_small": ("10", "Target number of small accounts (<50K)."),
    "min_posts_per_week": ("1", "Qualification: short videos per week (last 4 weeks)."),
    "max_days_since_post": ("30", "Qualification + pruning: must have posted within this many days."),
    "candidate_min_relevance": ("6", "Minimum AI relevance (0-10) for a discovered account."),
    "discovery_results_per_keyword": ("30", "Reels fetched per keyword during discovery."),
    "discovery_max_profiles": ("40", "Max new profiles to check per discovery run."),
    "monthly_new_accounts": ("5", "Suggest this many new accounts each month."),
    # --- Daily run sizing ---------------------------------------------------------------
    "reels_per_check": ("12", "Latest reels fetched per account per day."),
    "backfill_reels": ("40", "Reels fetched the first time an account is added (baseline + evergreen)."),
    "monthly_refresh_reels": ("25", "Reels fetched per account in the monthly baseline refresh."),
    "max_analyses_per_run": ("8", "Max approved outliers broken down by the AI per run (cost cap)."),
    # --- Scrapers (Apify) ---------------------------------------------------------------
    # Input templates are JSON. "{{usernames}}", "{{urls}}", "{{keywords}}" become lists;
    # "{{limit}}" becomes a number. Check the actor's "Input" tab on apify.com if a run fails.
    "reel_actor": ("dami_studio/instagram-reel-scraper", "Apify actor that lists a profile's reels."),
    "reel_actor_input": (
        '{"usernames": "{{usernames}}", "maxReels": "{{limit}}"}',
        "JSON input template for reel_actor.",
    ),
    "search_actor": ("dami_studio/instagram-reels-search-scraper", "Apify actor that searches reels by keyword."),
    "search_actor_input": (
        '{"keywords": "{{keywords}}", "maxResults": "{{limit}}"}',
        "JSON input template for search_actor.",
    ),
    "profile_actor": ("apify/instagram-profile-scraper", "Apify actor for follower counts, bio, latest posts."),
    "profile_actor_input": ('{"usernames": "{{usernames}}"}', "JSON input template for profile_actor."),
    "post_actor": ("apify/instagram-scraper", "Apify actor to re-fetch single reels by URL (fresh video link)."),
    "post_actor_input": (
        '{"directUrls": "{{urls}}", "resultsType": "posts", "resultsLimit": 1}',
        "JSON input template for post_actor.",
    ),
    "apify_price_per_1000": ("0.5", "Used only for the cost estimate in the run log."),
    # --- AI ---------------------------------------------------------------------------
    "analysis_model": ("claude-sonnet-5", "Claude model for the 7-brick breakdown, patterns and remixes."),
    "fast_model": ("claude-haiku-4-5", "Claude model for cheap relevance checks."),
    "transcription_model": ("whisper-large-v3", "Groq Whisper model (large-v3 is best for Hinglish)."),
    "max_frames": ("16", "Max video frames sent to the AI per reel."),
}


@dataclass
class Secrets:
    apify_token: str
    anthropic_api_key: str
    groq_api_key: str
    google_service_account_json: str
    sheet_id: str
    gmail_address: str
    gmail_app_password: str
    email_to: str

    @classmethod
    def from_env(cls) -> "Secrets":
        get = lambda k: os.environ.get(k, "").strip()  # noqa: E731
        return cls(
            apify_token=get("APIFY_TOKEN"),
            anthropic_api_key=get("ANTHROPIC_API_KEY"),
            groq_api_key=get("GROQ_API_KEY"),
            google_service_account_json=get("GOOGLE_SERVICE_ACCOUNT_JSON"),
            sheet_id=get("SHEET_ID"),
            gmail_address=get("GMAIL_ADDRESS"),
            gmail_app_password=get("GMAIL_APP_PASSWORD"),
            email_to=get("EMAIL_TO") or get("GMAIL_ADDRESS"),
        )

    def missing(self) -> list[str]:
        names = {
            "APIFY_TOKEN": self.apify_token,
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "GROQ_API_KEY": self.groq_api_key,
            "GOOGLE_SERVICE_ACCOUNT_JSON": self.google_service_account_json,
            "SHEET_ID": self.sheet_id,
            "GMAIL_ADDRESS": self.gmail_address,
            "GMAIL_APP_PASSWORD": self.gmail_app_password,
        }
        return [k for k, v in names.items() if not v]


class Settings:
    """Typed access to the key/value settings, with defaults for anything missing."""

    def __init__(self, values: dict[str, str] | None = None):
        self.values = {k: v for k, (v, _) in DEFAULTS.items()}
        for k, v in (values or {}).items():
            if str(v).strip() != "":
                self.values[k] = str(v).strip()

    def str(self, key: str) -> str:
        return self.values[key]

    def int(self, key: str) -> int:
        return int(float(self.values[key]))

    def float(self, key: str) -> float:
        return float(self.values[key])

    def list(self, key: str) -> list[str]:
        return [x.strip() for x in self.values[key].split(",") if x.strip()]

    def json(self, key: str):
        return json.loads(self.values[key])

    def adjacent_niches(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for part in self.values["adjacent_niches"].split("|"):
            if ":" not in part:
                continue
            name, kws = part.split(":", 1)
            out[name.strip()] = [k.strip() for k in kws.split(",") if k.strip()]
        return out
