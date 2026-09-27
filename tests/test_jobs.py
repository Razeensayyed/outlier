"""Run the daily/weekly jobs end-to-end against an in-memory sheet, fake scraper and fake AI."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from outlier import jobs, media
from outlier.ai import BrickPlan, Bricks, Relevance, Remix
from outlier.costs import Costs
from outlier.instagram import normalize_profile, normalize_reel
from outlier.settings import Settings
from outlier.sheets import TABS

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


class FakeTable:
    def __init__(self, headers):
        self.headers = list(headers)
        self.data: list[dict] = []
        self._pending = []

    def rows(self, refresh=False):
        return [{**{h: "" for h in self.headers}, **{k: ("" if v is None else v) for k, v in r.items()}, "_row": i + 2}
                for i, r in enumerate(self.data)]

    def append(self, records):
        for r in records:
            self.data.append({h: r.get(h) for h in self.headers})

    def update(self, row, changes):
        self._pending.append((row, changes))

    def flush(self):
        for row, changes in self._pending:
            self.data[row - 2].update({k: v for k, v in changes.items() if k in self.headers})
        self._pending = []

    def replace_all(self, records):
        self.data = []
        self.append(records)


class FakeSheet:
    url = "https://sheet"

    def __init__(self):
        self.tables = {n: FakeTable(h) for n, h in TABS.items()}

    def table(self, name):
        return self.tables[name]


class FakeScraper:
    def __init__(self, reels_by_owner, profiles=(), search=()):
        self.reels_by_owner = reels_by_owner
        self._profiles = list(profiles)
        self._search = list(search)
        self.calls = []

    def reels_for(self, usernames, limit):
        self.calls.append(("reels", tuple(usernames), limit))
        return {u: self.reels_by_owner.get(u, [])[:limit] for u in usernames}

    def profiles(self, usernames):
        return [p for p in self._profiles if p.username in usernames]

    def search_reels(self, keywords, limit):
        return self._search

    def reels_by_url(self, urls):
        return []


class FakeAI:
    def reel_relevance(self, handle, caption, transcript):
        return Relevance(score=2 if "cooking" in caption else 8, reason="fits")

    def account_relevance(self, handle, bio, captions):
        return Relevance(score=9 if "AI" in bio else 1, reason="bio")

    def bricks(self, **kw):
        return Bricks(topic="5 ChatGPT prompts", topic_theme="ChatGPT prompts", angle="save time",
                      hook_spoken="Ye 5 prompts...", hook_text="5 PROMPTS", hook_visual="phone close-up",
                      hook_style="List / countdown", story_structure="Listicle", structure_notes="hook -> 5 -> CTA",
                      visual_format="Screen recording", key_visuals="zooms", audio_type="Voice + background music",
                      audio_notes="lofi", gap="no examples shown")

    def group_topics(self, topics):
        return {i: "ChatGPT prompts" for i in range(len(topics))}

    def remix(self, outlier, whats_working):
        bricks = ["Topic", "Angle", "Hook", "Story structure", "Visual format", "Key visuals", "Audio"]
        return Remix(bricks=[BrickPlan(brick=b, decision="Hold" if b in ("Topic", "Audio") else "Remix",
                                       original="orig", plan="new") for b in bricks],
                     hook_options=["a", "b", "c"], script_outline="outline")


def mk(owner, i, views, days_ago, caption="AI tips", likes=None):
    return normalize_reel({
        "shortCode": f"{owner}{i}", "ownerUsername": owner, "videoPlayCount": views,
        "likesCount": views // 20 if likes is None else likes, "commentsCount": 5,
        "timestamp": (NOW - timedelta(days=days_ago)).isoformat(), "caption": caption,
        "videoUrl": f"https://cdn/{owner}{i}.mp4",
    })


@pytest.fixture
def ctx(monkeypatch):
    c = object.__new__(jobs.Ctx)
    c.job = "test"
    c.now = NOW
    c.costs = Costs()
    c.errors = []
    c.sheet = FakeSheet()
    c.settings = Settings()
    c._ai = FakeAI()
    c._stt = None
    c.emails = []
    c.email = lambda subject, sections: c.emails.append((subject, sections))
    monkeypatch.setattr(jobs, "transcript_for", lambda ctx, url: ("transcript", None, None))
    return c


def test_daily_end_to_end(ctx, monkeypatch):
    normal = [mk("alice", i, 1000 + 10 * i, 10 + 3 * i) for i in range(15)]
    outlier = mk("alice", 99, 20_000, 5)               # 20x -> outlier
    off_niche = mk("alice", 98, 30_000, 6, caption="my cooking vlog")  # outlier but off-niche
    young = mk("alice", 97, 50_000, 1)                 # too young to score
    ctx.scraper = FakeScraper(
        {"alice": [outlier, off_niche, young] + normal},
        profiles=[normalize_profile({"username": "alice", "followersCount": 40_000})],
    )
    ctx.sheet.table("Watch List").append([{"Handle": "@Alice"}])  # typed by hand

    jobs.run_daily(ctx)

    wl = ctx.sheet.table("Watch List").rows()[0]
    assert wl["Handle"] == "alice" and wl["Backfilled"] is True and wl["Tier"] == "Small"
    assert 1000 <= wl["Median views"] <= 1150 and wl["Status"] == "active"

    bank = ctx.sheet.table("Outlier Bank").rows()
    assert [b["Reel ID"] for b in bank] == ["alice99"]
    assert bank[0]["Status"] == "pending" and bank[0]["Window"] == "trend" and bank[0]["Outlier score"] >= 17
    reels = {r["Reel ID"]: r for r in ctx.sheet.table("Reels").rows()}
    assert reels["alice98"]["Status"].startswith("rejected: off-niche")
    assert reels["alice97"]["Score"] == ""  # not scored yet

    # Second day: user approves, views update, no duplicates; approved reel gets analyzed.
    ctx.sheet.table("Outlier Bank").update(2, {"Approve": True})
    ctx.sheet.table("Outlier Bank").flush()
    monkeypatch.setattr(media, "download", lambda url, dest: Path("/tmp/fake.mp4"))
    monkeypatch.setattr(media, "extract_frames", lambda *a, **k: [])
    monkeypatch.setattr(media, "extract_audio", lambda *a, **k: None)
    jobs.run_daily(ctx)
    assert ctx.scraper.calls[-1][2] == ctx.settings.int("reels_per_check")  # no second backfill
    bank = ctx.sheet.table("Outlier Bank").rows()
    assert len(bank) == 1 and bank[0]["Status"] == "analyzed" and bank[0]["Hook style"] == "List / countdown"

    # Third day: user ticks Pick -> remix lands in Script Queue.
    ctx.sheet.table("Outlier Bank").update(2, {"Pick": True})
    ctx.sheet.table("Outlier Bank").flush()
    jobs.run_daily(ctx)
    q = ctx.sheet.table("Script Queue").rows()
    assert len(q) == 1 and q[0]["Topic"] == "Hold" and q[0]["Hook"] == "Remix"
    assert ctx.sheet.table("Outlier Bank").rows()[0]["Status"] == "queued"
    assert not ctx.errors, ctx.errors
    assert len(ctx.sheet.table("Run Log").rows()) == 3


def test_weekly_patterns_and_discovery(ctx):
    bank = ctx.sheet.table("Outlier Bank")
    for i in range(4):
        bank.append([{"Reel ID": f"r{i}", "Date found": "2026-09-25", "Link": f"https://l/{i}", "Creator": "bob",
                      "Status": "analyzed", "Topic": "prompts", "Topic theme": "x", "Hook style": "Question",
                      "Story structure": "Listicle — a", "Visual format": "Talking head",
                      "Audio type": "Trending sound"}])
    bank.append([{"Reel ID": "old", "Date found": "2026-08-01", "Status": "analyzed", "Hook style": "Bold claim"}])
    ctx.scraper = FakeScraper(
        {}, search=[mk("newguy", 1, 5000, 2), mk("newguy", 2, 9000, 3), mk("chef", 1, 100, 2)],
        profiles=[normalize_profile({"username": "newguy", "followersCount": 600_000, "biography": "AI for business",
                                     "latestPosts": [{"shortCode": f"p{i}", "videoPlayCount": 10, "ownerUsername": "newguy",
                                                      "timestamp": (NOW - timedelta(days=i * 2)).isoformat()} for i in range(8)]}),
                  normalize_profile({"username": "chef", "followersCount": 1000, "biography": "recipes",
                                     "latestPosts": [{"shortCode": "q", "videoPlayCount": 1, "timestamp": NOW.isoformat()}]})],
    )
    jobs.run_weekly(ctx)
    ww = ctx.sheet.table("What's Working Now").rows()
    top_hook = next(r for r in ww if r["Category"] == "Hook style")
    assert top_hook["Pattern"] == "🔥 Question" and top_hook["Count"] == 4
    assert all("Bold claim" not in r["Pattern"] for r in ww)  # older than 7 days
    cands = ctx.sheet.table("Candidates").rows()
    assert [c["Handle"] for c in cands] == ["newguy"] and cands[0]["Tier"] == "Big"
