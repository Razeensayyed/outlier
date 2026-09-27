"""Normalize the raw JSON that different Apify Instagram actors return.

Cheap third-party actors all name their fields slightly differently, so every field is
looked up under several common names. `missing_fields()` tells you which ones a given
actor doesn't provide (run `python -m outlier check`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _get(d: dict, *paths: str) -> Any:
    """Return the first non-empty value among dotted paths like 'owner.username'."""
    for path in paths:
        cur: Any = d
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                cur = None
                break
        if cur not in (None, "", [], {}):
            return cur
    return None


def _int(v: Any) -> int | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None  # Instagram uses -1 for "hidden"


def _bool(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes"}
    return bool(v)


def parse_time(v: Any) -> datetime | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
        n = float(v)
        if n > 1e12:  # milliseconds
            n /= 1000
        return datetime.fromtimestamp(n, tz=timezone.utc)
    s = str(v).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class Reel:
    id: str
    shortcode: str
    url: str
    owner: str
    posted_at: datetime | None
    views: int | None
    likes: int | None
    comments: int | None
    shares: int | None
    duration: float | None
    caption: str
    pinned: bool
    paid: bool
    coauthors: list[str]
    audio: str
    original_audio: bool | None
    video_url: str
    is_video: bool
    raw_keys: list[str] = field(default_factory=list)

    @property
    def engagement(self) -> int | None:
        parts = [self.likes, self.comments, self.shares]
        if all(p is None for p in parts):
            return None
        return sum(p or 0 for p in parts)

    def missing_fields(self) -> list[str]:
        checks = {
            "views": self.views,
            "likes": self.likes,
            "comments": self.comments,
            "posted_at": self.posted_at,
            "owner": self.owner,
            "video_url": self.video_url,
            "caption": self.caption,
            "audio": self.audio,
        }
        return [k for k, v in checks.items() if v in (None, "")]


def normalize_reel(item: dict, default_owner: str = "") -> Reel:
    shortcode = str(_get(item, "shortCode", "shortcode", "code") or "")
    rid = str(_get(item, "id", "pk", "postId", "reelId") or shortcode)
    url = _get(item, "url", "reelUrl", "postUrl", "permalink", "link") or ""
    if not url and shortcode:
        url = f"https://www.instagram.com/reel/{shortcode}/"
    if not shortcode and "/reel/" in url:
        shortcode = url.rstrip("/").split("/")[-1]
    if not rid:
        rid = shortcode or url

    caption = _get(item, "caption.text", "caption", "text", "description") or ""
    if not isinstance(caption, str):
        caption = str(caption)

    music = _get(item, "musicInfo", "music", "audio", "clipsMusicAttributionInfo") or {}
    audio = ""
    original = None
    if isinstance(music, dict):
        song = _get(music, "song_name", "songName", "title", "name", "audio_name")
        artist = _get(music, "artist_name", "artistName", "artist", "author")
        audio = " - ".join(str(x) for x in (song, artist) if x)
        orig = _get(music, "uses_original_audio", "usesOriginalAudio", "isOriginal", "original")
        original = _bool(orig) if orig is not None else None
    elif isinstance(music, str):
        audio = music

    coauthors_raw = _get(item, "coauthorUsernames", "coauthors", "coauthorProducers") or []
    coauthors = []
    for c in coauthors_raw if isinstance(coauthors_raw, list) else []:
        name = c.get("username") if isinstance(c, dict) else c
        if name:
            coauthors.append(str(name))

    typ = str(_get(item, "type", "productType", "mediaType", "media_type") or "").lower()
    video_url = _get(item, "videoUrl", "video_url", "videoUrlHd", "downloadUrl", "video.url") or ""
    views = _int(_get(item, "videoPlayCount", "playCount", "play_count", "plays", "videoViewCount",
                      "viewCount", "view_count", "views"))
    is_video = bool(video_url) or views is not None or typ in {"video", "clips", "reel", "2"}

    return Reel(
        id=rid,
        shortcode=shortcode,
        url=url,
        owner=str(_get(item, "ownerUsername", "owner.username", "username", "author.username", "author")
                  or default_owner).lower().lstrip("@"),
        posted_at=parse_time(_get(item, "timestamp", "takenAt", "taken_at", "createdAt", "created_at",
                                  "date", "postedAt")),
        views=views,
        likes=_int(_get(item, "likesCount", "likeCount", "like_count", "likes")),
        comments=_int(_get(item, "commentsCount", "commentCount", "comment_count", "comments")),
        shares=_int(_get(item, "sharesCount", "shareCount", "reshareCount", "share_count", "shares")),
        duration=(lambda d: float(d) if d is not None else None)(
            _get(item, "videoDuration", "duration", "video_duration")
        ),
        caption=caption,
        pinned=_bool(_get(item, "isPinned", "is_pinned", "pinned")),
        paid=_bool(_get(item, "paidPartnership", "isPaidPartnership", "is_paid_partnership", "isSponsored",
                        "sponsored", "isAd", "is_ad")),
        coauthors=coauthors,
        audio=audio,
        original_audio=original,
        video_url=str(video_url),
        is_video=is_video,
        raw_keys=sorted(item.keys()),
    )


@dataclass
class Profile:
    username: str
    full_name: str
    followers: int | None
    bio: str
    is_private: bool
    posts: list[Reel]

    @property
    def url(self) -> str:
        return f"https://www.instagram.com/{self.username}/"


def normalize_profile(item: dict) -> Profile:
    username = str(_get(item, "username", "userName", "handle") or "").lower().lstrip("@")
    latest = _get(item, "latestPosts", "latestReels", "posts", "recentPosts") or []
    posts = [normalize_reel(p, username) for p in latest if isinstance(p, dict)]
    return Profile(
        username=username,
        full_name=str(_get(item, "fullName", "full_name", "name") or ""),
        followers=_int(_get(item, "followersCount", "followers", "follower_count", "edge_followed_by.count")),
        bio=str(_get(item, "biography", "bio", "description") or ""),
        is_private=_bool(_get(item, "private", "isPrivate", "is_private")),
        posts=posts,
    )
