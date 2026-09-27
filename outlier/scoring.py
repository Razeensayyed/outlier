"""Pure math for baselines, outlier scores and the automated validation checks."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

from .instagram import Reel


@dataclass
class Baseline:
    median_views: float | None
    engagement_rate: float | None  # median (likes+comments+shares)/views
    sample_size: int
    confidence: str  # "ok" | "low" | "none"


def engagement_rate(reel: Reel) -> float | None:
    if not reel.views or reel.engagement is None:
        return None
    return reel.engagement / reel.views


def age_days(reel: Reel, now: datetime) -> float | None:
    if reel.posted_at is None:
        return None
    return (now - reel.posted_at).total_seconds() / 86400


def compute_baseline(
    reels: list[Reel],
    now: datetime,
    *,
    sample: int = 20,
    min_age_days: float = 7,
    min_sample: int = 10,
    boost_ratio_floor: float = 0.3,
    exclude_id: str | None = None,
) -> Baseline:
    """Median views over the most recent `sample` eligible reels.

    Eligible = has views + date, at least `min_age_days` old, not pinned, not paid,
    and not a suspected boost (engagement far below the creator's typical ratio).
    The reel being scored (`exclude_id`) never counts toward its own baseline.
    """
    eligible = [
        r for r in reels
        if r.id != exclude_id
        and r.views is not None
        and r.posted_at is not None
        and not r.pinned
        and not r.paid
        and (age_days(r, now) or 0) >= min_age_days
    ]
    eligible.sort(key=lambda r: r.posted_at, reverse=True)
    eligible = eligible[: sample + 5]  # small buffer for boost removal below

    rates = [x for x in (engagement_rate(r) for r in eligible) if x is not None]
    typical_rate = statistics.median(rates) if rates else None
    if typical_rate:
        eligible = [
            r for r in eligible
            if engagement_rate(r) is None or engagement_rate(r) >= boost_ratio_floor * typical_rate
        ]
    eligible = eligible[:sample]

    if not eligible:
        return Baseline(None, typical_rate, 0, "none")
    median = statistics.median(r.views for r in eligible)
    confidence = "ok" if len(eligible) >= min_sample else "low"
    return Baseline(float(median), typical_rate, len(eligible), confidence)


def outlier_score(views: int | None, median: float | None) -> float | None:
    if views is None or not median:
        return None
    return round(views / median, 2)


def window_label(reel: Reel, now: datetime, trend_days: int, evergreen_days: int) -> str | None:
    a = age_days(reel, now)
    if a is None:
        return None
    if a <= trend_days:
        return "trend"
    if a <= evergreen_days:
        return "evergreen"
    return None


def old_enough(reel: Reel, now: datetime, min_age_hours: float) -> bool:
    return reel.posted_at is not None and now - reel.posted_at >= timedelta(hours=min_age_hours)


def validate_real(
    reel: Reel,
    baseline: Baseline,
    *,
    boost_ratio_floor: float,
    reject_terms: list[str],
) -> tuple[bool, str]:
    """The automated half of Phase 5 ('Real?'). Returns (ok, note)."""
    if reel.paid:
        return False, "paid partnership"
    caption = reel.caption.lower()
    for term in reject_terms:
        t = term.lower().strip()
        if not t:
            continue
        # whole-word match, so '#ad' doesn't hit '#adobe' and 'ad' doesn't hit 'download'
        if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", caption):
            return False, f"caption contains '{term.strip()}'"
    rate = engagement_rate(reel)
    if rate is not None and baseline.engagement_rate:
        ratio = rate / baseline.engagement_rate
        if ratio < boost_ratio_floor:
            return False, f"suspect boost (engagement {ratio:.2f}x usual)"
        note = f"engagement {ratio:.2f}x usual"
    else:
        note = "engagement unknown"
    if reel.coauthors:
        note += f"; collab with {', '.join(reel.coauthors)}"
    return True, note


def tier(followers: int | None) -> str:
    if followers is None:
        return "?"
    if followers >= 500_000:
        return "Big"
    if followers >= 50_000:
        return "Mid"
    return "Small"


def posts_per_week(reels: list[Reel], now: datetime, weeks: int = 4) -> float:
    cutoff = now - timedelta(weeks=weeks)
    n = sum(1 for r in reels if r.is_video and r.posted_at and r.posted_at >= cutoff)
    return round(n / weeks, 2)


def days_since_last_post(reels: list[Reel], now: datetime) -> float | None:
    dates = [r.posted_at for r in reels if r.posted_at]
    if not dates:
        return None
    return round((now - max(dates)).total_seconds() / 86400, 1)
