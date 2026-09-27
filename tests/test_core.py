from datetime import datetime, timedelta, timezone

from outlier import scoring
from outlier.instagram import normalize_profile, normalize_reel
from outlier.scraper import fill_template
from outlier.settings import Settings

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


def reel(i, views, days_ago, likes=None, comments=10, pinned=False, paid=False, caption=""):
    likes = views // 20 if likes is None else likes
    return normalize_reel({
        "shortCode": f"c{i}", "ownerUsername": "creator", "videoPlayCount": views,
        "likesCount": likes, "commentsCount": comments, "isPinned": pinned, "paidPartnership": paid,
        "timestamp": (NOW - timedelta(days=days_ago)).isoformat(), "caption": caption,
        "videoUrl": "https://cdn/x.mp4",
    })


def test_normalize_official_style_fields():
    r = normalize_reel({
        "id": "1", "shortCode": "ABC", "ownerUsername": "Some_User", "videoPlayCount": 12345,
        "likesCount": -1, "commentsCount": 7, "timestamp": "2026-09-20T10:00:00.000Z",
        "musicInfo": {"song_name": "Original audio", "artist_name": "some_user", "uses_original_audio": True},
        "isPinned": True, "coauthorProducers": [{"username": "brand"}], "videoUrl": "https://x/v.mp4",
    })
    assert r.shortcode == "ABC" and r.url == "https://www.instagram.com/reel/ABC/"
    assert r.owner == "some_user" and r.views == 12345
    assert r.likes is None  # -1 means hidden
    assert r.pinned and r.coauthors == ["brand"] and r.original_audio is True
    assert r.posted_at == datetime(2026, 9, 20, 10, tzinfo=timezone.utc)
    assert "likes" in r.missing_fields()


def test_normalize_alternate_field_names():
    r = normalize_reel({
        "code": "XYZ", "username": "@Other", "playCount": "999", "likeCount": 10, "comment_count": 2,
        "taken_at": 1_758_000_000, "caption": {"text": "hello"}, "music": {"title": "Song", "artist": "A"},
    })
    assert r.owner == "other" and r.views == 999 and r.likes == 10 and r.comments == 2
    assert r.caption == "hello" and r.audio == "Song - A" and r.posted_at is not None


def test_normalize_profile():
    p = normalize_profile({"username": "Biz", "followersCount": 60000, "biography": "AI tips",
                           "latestPosts": [{"shortCode": "a", "videoPlayCount": 5, "timestamp": NOW.isoformat()}]})
    assert p.username == "biz" and p.followers == 60000 and len(p.posts) == 1 and p.posts[0].owner == "biz"
    assert scoring.tier(p.followers) == "Mid"


def test_baseline_excludes_pinned_paid_young_and_self():
    reels = [reel(i, 1000 + i, 10 + i) for i in range(12)]
    reels += [reel(100, 10_000_000, 30, pinned=True), reel(101, 9_000_000, 30, paid=True),
              reel(102, 5_000_000, 2)]  # too young
    b = scoring.compute_baseline(reels, NOW, sample=20, min_age_days=7, min_sample=10)
    assert b.sample_size == 12 and b.confidence == "ok"
    assert 1000 <= b.median_views <= 1012
    b2 = scoring.compute_baseline(reels, NOW, exclude_id=reels[0].id)
    assert b2.sample_size == 11


def test_baseline_drops_boosted_reels():
    reels = [reel(i, 1000, 10 + i) for i in range(10)]
    reels.append(reel(50, 1_000_000, 12, likes=5, comments=0))  # huge views, no engagement
    b = scoring.compute_baseline(reels, NOW, boost_ratio_floor=0.3)
    assert b.median_views == 1000 and b.sample_size == 10


def test_score_window_and_age():
    r = reel(1, 50_000, 5)
    assert scoring.outlier_score(r.views, 10_000) == 5.0
    assert scoring.window_label(r, NOW, 14, 180) == "trend"
    assert scoring.window_label(reel(2, 1, 100), NOW, 14, 180) == "evergreen"
    assert scoring.window_label(reel(3, 1, 200), NOW, 14, 180) is None
    assert scoring.old_enough(reel(4, 1, 1), NOW, 48) is False
    assert scoring.old_enough(reel(5, 1, 3), NOW, 48) is True


def test_validate_real():
    base = scoring.Baseline(1000, 0.06, 15, "ok")
    ok, note = scoring.validate_real(reel(1, 10_000, 5), base, boost_ratio_floor=0.3, reject_terms=["giveaway", "#ad"])
    assert ok and "engagement" in note
    assert scoring.validate_real(reel(2, 10_000, 5, paid=True), base, boost_ratio_floor=0.3, reject_terms=[])[0] is False
    assert scoring.validate_real(reel(3, 10_000, 5, caption="Big GIVEAWAY!"), base, boost_ratio_floor=0.3,
                                 reject_terms=["giveaway"])[0] is False
    assert scoring.validate_real(reel(4, 10_000, 5, caption="#adobe tips"), base, boost_ratio_floor=0.3,
                                 reject_terms=["#ad "])[0] is True
    assert scoring.validate_real(reel(5, 10_000, 5, caption="download the app"), base, boost_ratio_floor=0.3,
                                 reject_terms=["ad"])[0] is True  # word boundary: 'download' != 'ad'
    boosted = reel(6, 100_000, 5, likes=10, comments=0)
    ok, note = scoring.validate_real(boosted, base, boost_ratio_floor=0.3, reject_terms=[])
    assert not ok and "boost" in note


def test_posts_per_week():
    reels = [reel(i, 1, i * 3) for i in range(10)]  # every 3 days
    assert scoring.posts_per_week(reels, NOW) == 2.5  # 10 posts in 28 days
    assert scoring.days_since_last_post(reels, NOW) == 0


def test_fill_template():
    t = {"usernames": "{{usernames}}", "maxReels": "{{limit}}", "note": "for {{limit}} reels", "x": [1]}
    out = fill_template(t, {"usernames": ["a", "b"], "limit": 5})
    assert out == {"usernames": ["a", "b"], "maxReels": 5, "note": "for 5 reels", "x": [1]}


def test_settings_defaults_and_overrides():
    s = Settings({"outlier_threshold": "3", "seed_keywords": "a, b ,,c", "niche_statement": ""})
    assert s.float("outlier_threshold") == 3.0
    assert s.list("seed_keywords") == ["a", "b", "c"]
    assert s.str("niche_statement")  # blank falls back to default
    assert "entrepreneurship" in s.adjacent_niches()
    assert isinstance(s.json("reel_actor_input"), dict)
