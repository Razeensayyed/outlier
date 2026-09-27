"""The scheduled jobs: discover, daily, weekly, monthly (plus init/check helpers).

Phase map
  1  Niche ..................... Settings tab (edit any time)
  2  Watch list ................ discover()  -> Candidates tab -> you tick Approve
  3  Baselines ................. refresh_watch_stats() (daily from stored reels, deep refresh monthly)
  4  Hunt ...................... hunt()
  5  Validate .................. hunt(): Real? + Relevant? automatically; Interesting? = you tick Approve
  6  Outlier Bank .............. analyze_approved()
  7  Weekly patterns ........... weekly()
  8  Pick & remix .............. you tick Pick -> remix_picked() -> Script Queue
  9  Maintain .................. monthly()
"""

from __future__ import annotations

import logging
import tempfile
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import emailer, media, scoring
from .ai import AI
from .costs import Costs
from .instagram import Profile, Reel, parse_time
from .scraper import Scraper
from .settings import DEFAULTS, Secrets, Settings
from .sheets import Sheet, truthy
from .transcribe import Transcriber

log = logging.getLogger(__name__)

MAX_NEW_OUTLIERS_PER_RUN = 40


# ---------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------

def fmt_dt(dt: datetime | None) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") if dt else ""


def fmt_date(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def num(v) -> float | None:
    s = str(v).replace(",", "").replace("x", "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def clean_handle(h: str) -> str:
    h = str(h).strip()
    if "instagram.com/" in h:
        h = h.split("instagram.com/", 1)[1].split("/")[0].split("?")[0]
    return h.lstrip("@").strip().lower()


def reel_key(r: Reel) -> str:
    return r.shortcode or r.id


def row_to_reel(row: dict) -> Reel:
    return Reel(
        id=row.get("Reel ID", ""),
        shortcode=row.get("Reel ID", ""),
        url=row.get("URL", ""),
        owner=clean_handle(row.get("Handle", "")),
        posted_at=parse_time(row.get("Posted")),
        views=(lambda n: int(n) if n is not None else None)(num(row.get("Views"))),
        likes=(lambda n: int(n) if n is not None else None)(num(row.get("Likes"))),
        comments=(lambda n: int(n) if n is not None else None)(num(row.get("Comments"))),
        shares=(lambda n: int(n) if n is not None else None)(num(row.get("Shares"))),
        duration=num(row.get("Duration")),
        caption=row.get("Caption", ""),
        pinned=truthy(row.get("Pinned")),
        paid=truthy(row.get("Paid")),
        coauthors=[c.strip() for c in str(row.get("Coauthors", "")).split(",") if c.strip()],
        audio=row.get("Audio", ""),
        original_audio=None,
        video_url=row.get("Video URL", ""),
        is_video=True,
    )


class Ctx:
    """Everything a job needs, created once per run."""

    def __init__(self, job: str):
        self.job = job
        self.secrets = Secrets.from_env()
        missing = self.secrets.missing()
        if missing:
            raise SystemExit(f"Missing secrets: {', '.join(missing)} (add them as GitHub Actions secrets)")
        self.now = datetime.now(timezone.utc)
        self.costs = Costs()
        self.errors: list[str] = []
        self.sheet = Sheet(self.secrets.google_service_account_json, self.secrets.sheet_id)
        self.sheet.ensure_all()
        self.settings = load_settings(self.sheet)
        self.scraper = Scraper(self.secrets.apify_token, self.settings, self.costs)
        self._ai: AI | None = None
        self._stt: Transcriber | None = None

    @property
    def ai(self) -> AI:
        if self._ai is None:
            s = self.settings
            self._ai = AI(self.secrets.anthropic_api_key, s.str("analysis_model"), s.str("fast_model"),
                          self.costs, s.str("niche_statement"), s.str("content_language"))
        return self._ai

    @property
    def stt(self) -> Transcriber:
        if self._stt is None:
            self._stt = Transcriber(self.secrets.groq_api_key, self.settings.str("transcription_model"), self.costs)
        return self._stt

    def error(self, where: str, exc: BaseException) -> None:
        msg = f"{where}: {type(exc).__name__}: {exc}"
        log.error(msg)
        log.debug(traceback.format_exc())
        self.errors.append(msg)

    def log_run(self, status: str, summary: str) -> None:
        row = {"Time": fmt_dt(self.now), "Job": self.job, "Status": status, "Summary": summary,
               "Errors": "\n".join(self.errors)[:5000], **self.costs.row()}
        self.sheet.table("Run Log").append([row])

    def email(self, subject: str, sections: list[tuple[str, str]]) -> None:
        if self.errors:
            sections = sections + [("Problems", "<ul>" + "".join(f"<li>{emailer.esc(e)}</li>" for e in self.errors) + "</ul>")]
        sections = sections + [("Cost of this run", f"<p>≈ ${self.costs.total:.3f} "
                                f"(Apify ${self.costs.apify_usd:.3f} · Claude ${self.costs.claude_usd:.3f} · "
                                f"Groq ${self.costs.groq_usd:.4f})</p>")]
        body = emailer.page(subject, sections, self.sheet.url)
        emailer.send(self.secrets.gmail_address, self.secrets.gmail_app_password, self.secrets.email_to, subject, body)


def load_settings(sheet: Sheet) -> Settings:
    t = sheet.table("Settings")
    rows = t.rows()
    values = {r["Key"].strip(): r["Value"] for r in rows if r.get("Key")}
    missing = [k for k in DEFAULTS if k not in values]
    if missing:
        t.append([{"Key": k, "Value": DEFAULTS[k][0], "Description": DEFAULTS[k][1]} for k in missing])
    return Settings(values)


# ---------------------------------------------------------------------------------------
# watch list + reels storage
# ---------------------------------------------------------------------------------------

def watched(ctx: Ctx) -> list[dict]:
    rows = ctx.sheet.table("Watch List").rows()
    return [r for r in rows if clean_handle(r.get("Handle", "")) and r.get("Status", "").strip().lower() != "dropped"]


def upsert_reels(ctx: Ctx, by_owner: dict[str, list[Reel]]) -> set[str]:
    """Insert new reels / refresh stats on known ones. Returns the keys touched this run."""
    t = ctx.sheet.table("Reels")
    existing = {r["Reel ID"]: r for r in t.rows() if r.get("Reel ID")}
    touched: set[str] = set()
    new_rows = []
    now = fmt_dt(ctx.now)
    for owner, reels in by_owner.items():
        for r in reels:
            k = reel_key(r)
            if not k or k in touched:
                continue
            touched.add(k)
            fields = {
                "Views": r.views, "Likes": r.likes, "Comments": r.comments, "Shares": r.shares,
                "Pinned": r.pinned, "Paid": r.paid, "Video URL": r.video_url, "Last checked": now,
            }
            if k in existing:
                # Never overwrite a known number with "unknown".
                ctx.sheet.table("Reels").update(existing[k]["_row"], {f: v for f, v in fields.items() if v not in (None, "")})
            else:
                new_rows.append({
                    "Reel ID": k, "Handle": owner, "URL": r.url, "Posted": fmt_dt(r.posted_at),
                    "Duration": r.duration, "Coauthors": ", ".join(r.coauthors), "Audio": r.audio,
                    "Caption": r.caption, "First seen": now, **fields,
                })
    t.flush()
    t.append(new_rows)
    return touched


def reels_by_owner(ctx: Ctx) -> tuple[dict[str, list[Reel]], dict[str, dict]]:
    rows = ctx.sheet.table("Reels").rows(refresh=True)
    by_owner: dict[str, list[Reel]] = defaultdict(list)
    by_key: dict[str, dict] = {}
    for row in rows:
        r = row_to_reel(row)
        by_owner[r.owner].append(r)
        by_key[row["Reel ID"]] = row
    return by_owner, by_key


def baseline_for(ctx: Ctx, reels: list[Reel], exclude: str | None = None) -> scoring.Baseline:
    s = ctx.settings
    return scoring.compute_baseline(
        reels, ctx.now,
        sample=s.int("baseline_sample"),
        min_age_days=s.float("baseline_min_age_days"),
        min_sample=s.int("baseline_min_sample"),
        boost_ratio_floor=s.float("boost_ratio_floor"),
        exclude_id=exclude,
    )


def refresh_watch_stats(ctx: Ctx, profiles: dict[str, Profile] | None = None) -> None:
    """Phase 3: recompute every account's median from the stored reels."""
    by_owner, _ = reels_by_owner(ctx)
    bank = ctx.sheet.table("Outlier Bank").rows(refresh=True)
    month_ago = ctx.now - timedelta(days=30)
    last_outlier: dict[str, str] = {}
    outliers_30d: Counter = Counter()
    for b in bank:
        h = clean_handle(b.get("Creator", ""))
        d = b.get("Date found", "")
        if d > last_outlier.get(h, ""):
            last_outlier[h] = d
        found = parse_time(d)
        if found and found >= month_ago:
            outliers_30d[h] += 1

    wl = ctx.sheet.table("Watch List")
    for row in watched(ctx):
        h = clean_handle(row["Handle"])
        reels = by_owner.get(h, [])
        b = baseline_for(ctx, reels)
        changes = {
            "Handle": h,
            "Platform": row.get("Platform") or "Instagram",
            "Link": row.get("Link") or f"https://www.instagram.com/{h}/",
            "Median views": round(b.median_views) if b.median_views else "",
            "Engagement rate": round(b.engagement_rate, 4) if b.engagement_rate else "",
            "Sample size": b.sample_size,
            "Confidence": b.confidence,
            "Posts/week": scoring.posts_per_week(reels, ctx.now),
            "Last post": fmt_dt(max((r.posted_at for r in reels if r.posted_at), default=None)),
            "Last outlier": last_outlier.get(h, ""),
            "Outliers (30d)": outliers_30d.get(h, 0),
            "Status": row.get("Status") or "active",
            "Last updated": fmt_dt(ctx.now),
        }
        p = (profiles or {}).get(h)
        if p and p.followers is not None:
            changes["Followers"] = p.followers
            changes["Tier"] = scoring.tier(p.followers)
        wl.update(row["_row"], changes)
    wl.flush()


def fetch_watchlist_reels(ctx: Ctx, limit: int, only_new: bool = False) -> set[str]:
    """Scrape the latest reels for watched accounts (backfilling brand-new ones deeper)."""
    s = ctx.settings
    wl = ctx.sheet.table("Watch List")
    accounts = watched(ctx)
    new = [r for r in accounts if not truthy(r.get("Backfilled"))]
    old = [r for r in accounts if truthy(r.get("Backfilled"))]
    touched: set[str] = set()

    if new:
        handles = [clean_handle(r["Handle"]) for r in new]
        try:
            got = ctx.scraper.reels_for(handles, s.int("backfill_reels"))
            touched |= upsert_reels(ctx, got)
            for r in new:
                if got.get(clean_handle(r["Handle"])):
                    wl.update(r["_row"], {"Backfilled": True, "Added": r.get("Added") or fmt_date(ctx.now)})
            wl.flush()
            empty = [h for h in handles if not got.get(h)]
            if empty:
                ctx.errors.append(f"No reels returned for: {', '.join(empty)} (private, renamed, or scraper issue)")
        except Exception as e:  # noqa: BLE001
            ctx.error("backfill scrape", e)

    if old and not only_new:
        handles = [clean_handle(r["Handle"]) for r in old]
        try:
            touched |= upsert_reels(ctx, ctx.scraper.reels_for(handles, limit))
        except Exception as e:  # noqa: BLE001
            ctx.error("daily scrape", e)

    # Manually typed handles have no follower count yet - look them up once (cheap).
    need = [clean_handle(r["Handle"]) for r in watched(ctx) if not str(r.get("Followers", "")).strip()]
    profiles = {}
    if need:
        try:
            profiles = {p.username: p for p in ctx.scraper.profiles(need)}
        except Exception as e:  # noqa: BLE001
            ctx.error("profile lookup", e)
    refresh_watch_stats(ctx, profiles)
    return touched


def promote_candidates(ctx: Ctx) -> list[str]:
    """Approved candidates move onto the watch list."""
    ct = ctx.sheet.table("Candidates")
    wl = ctx.sheet.table("Watch List")
    existing = {clean_handle(r.get("Handle", "")) for r in wl.rows()}
    added = []
    for row in ct.rows():
        if not truthy(row.get("Approve")) or row.get("Status", "").lower() == "added":
            continue
        h = clean_handle(row["Handle"])
        if h and h not in existing:
            wl.append([{
                "Handle": h, "Platform": "Instagram", "Link": f"https://www.instagram.com/{h}/",
                "Followers": (lambda n: int(n) if n is not None else "")(num(row.get("Followers"))), "Tier": row.get("Tier"), "Status": "active",
                "Added": fmt_date(ctx.now), "Backfilled": False,
            }])
            existing.add(h)
            added.append(h)
        ct.update(row["_row"], {"Status": "added"})
    ct.flush()
    return added


# ---------------------------------------------------------------------------------------
# Phase 4 + 5: hunt and validate
# ---------------------------------------------------------------------------------------

def transcript_for(ctx: Ctx, video_url: str) -> tuple[str, Path | None, tempfile.TemporaryDirectory | None]:
    """Download + transcribe. Returns (transcript, video_path, tmpdir-to-keep-alive)."""
    if not video_url:
        return "", None, None
    tmp = tempfile.TemporaryDirectory()
    d = Path(tmp.name)
    video = media.download(video_url, d / "reel.mp4")
    audio = media.extract_audio(video, d / "audio.mp3")
    text = ""
    if audio:
        text = ctx.stt.transcribe(audio, media.duration(video))
    return text, video, tmp


def hunt(ctx: Ctx, touched: set[str]) -> list[dict]:
    s = ctx.settings
    threshold = s.float("outlier_threshold")
    reject_terms = s.list("reject_caption_terms")
    by_owner, by_key = reels_by_owner(ctx)
    bank = ctx.sheet.table("Outlier Bank")
    in_bank = {r.get("Reel ID") for r in bank.rows()}
    reels_t = ctx.sheet.table("Reels")
    watched_handles = {clean_handle(r["Handle"]) for r in watched(ctx)}

    new_rows: list[dict] = []
    for key in touched:
        row = by_key.get(key)
        if not row or key in in_bank or row.get("Status", "").startswith("rejected"):
            continue
        reel = row_to_reel(row)
        if reel.owner not in watched_handles:
            continue
        window = scoring.window_label(reel, ctx.now, s.int("trend_window_days"), s.int("evergreen_window_days"))
        if window is None or not scoring.old_enough(reel, ctx.now, s.float("min_reel_age_hours")):
            continue
        base = baseline_for(ctx, by_owner.get(reel.owner, []), exclude=reel.id)
        score = scoring.outlier_score(reel.views, base.median_views)
        if score is None:
            continue
        reels_t.update(row["_row"], {"Score": score})
        if score < threshold:
            continue
        if len(new_rows) >= MAX_NEW_OUTLIERS_PER_RUN:
            break

        ok, note = scoring.validate_real(reel, base, boost_ratio_floor=s.float("boost_ratio_floor"),
                                         reject_terms=reject_terms)
        if not ok:
            reels_t.update(row["_row"], {"Status": f"rejected: {note}"})
            continue

        transcript = ""
        tmp = None
        try:
            transcript, _, tmp = transcript_for(ctx, reel.video_url)
        except Exception as e:  # noqa: BLE001 - relevance can still use the caption
            log.warning("transcript failed for %s: %s", reel.url, e)
        finally:
            if tmp:
                tmp.cleanup()
        try:
            rel = ctx.ai.reel_relevance(reel.owner, reel.caption, transcript)
        except Exception as e:  # noqa: BLE001
            ctx.error(f"relevance {reel.url}", e)
            continue
        if rel.score < s.int("relevance_min"):
            reels_t.update(row["_row"], {"Status": f"rejected: off-niche ({rel.score}/10) {rel.reason}"})
            continue

        reels_t.update(row["_row"], {"Status": "outlier"})
        new_rows.append({
            "Reel ID": key, "Date found": fmt_date(ctx.now), "Link": reel.url, "Creator": reel.owner,
            "Views": reel.views, "Median": round(base.median_views), "Outlier score": score, "Window": window,
            "Real check": note + ("" if base.confidence == "ok" else f"; baseline {base.confidence} confidence"),
            "Relevance": rel.score, "Relevance reason": rel.reason, "Approve": False, "Status": "pending",
            "Pick": False, "Transcript": transcript, "Caption": reel.caption,
        })
    reels_t.flush()
    new_rows.sort(key=lambda r: r["Outlier score"], reverse=True)
    bank.append(new_rows)
    return new_rows


# ---------------------------------------------------------------------------------------
# Phase 6: 7-brick breakdown of approved outliers
# ---------------------------------------------------------------------------------------

def analyze_approved(ctx: Ctx) -> list[dict]:
    s = ctx.settings
    bank = ctx.sheet.table("Outlier Bank")
    todo = [r for r in bank.rows(refresh=True)
            if truthy(r.get("Approve")) and (r.get("Status") in ("pending", "") or r.get("Status", "").startswith("error"))]
    todo = todo[: s.int("max_analyses_per_run")]
    if not todo:
        return []
    _, by_key = reels_by_owner(ctx)

    # Stored video links expire after a few days; re-fetch the ones that fail in one Apify call.
    tmpdirs: dict[str, tempfile.TemporaryDirectory] = {}
    videos: dict[str, Path] = {}

    def try_download(row: dict, url: str) -> bool:
        if not url:
            return False
        tmp = tempfile.TemporaryDirectory()
        try:
            videos[row["Reel ID"]] = media.download(url, Path(tmp.name) / "reel.mp4")
            tmpdirs[row["Reel ID"]] = tmp
            return True
        except Exception:  # noqa: BLE001
            tmp.cleanup()
            return False

    failed = [r for r in todo if not try_download(r, by_key.get(r["Reel ID"], {}).get("Video URL", ""))]
    if failed:
        try:
            fresh = ctx.scraper.reels_by_url([r["Link"] for r in failed])
            by_code = {reel_key(x): x for x in fresh}
            for r in failed:
                x = by_code.get(r["Reel ID"]) or next((y for y in fresh if y.url.rstrip("/") == r["Link"].rstrip("/")), None)
                if x:
                    try_download(r, x.video_url)
        except Exception as e:  # noqa: BLE001
            ctx.error("re-fetch video links", e)

    done = []
    for row in todo:
        rid = row["Reel ID"]
        try:
            if rid not in videos:
                raise RuntimeError("could not download the video")
            video = videos[rid]
            workdir = video.parent
            transcript = row.get("Transcript", "")
            if not transcript:
                audio = media.extract_audio(video, workdir / "audio.mp3")
                if audio:
                    transcript = ctx.stt.transcribe(audio, media.duration(video))
            frames = media.extract_frames(video, workdir, s.int("max_frames"))
            reel_row = by_key.get(rid, {})
            b = ctx.ai.bricks(
                handle=row.get("Creator", ""), views=int(num(row.get("Views")) or 0),
                score=num(row.get("Outlier score")) or 0, caption=row.get("Caption", ""),
                audio=reel_row.get("Audio", ""), transcript=transcript, frames=frames,
            )
            changes = {
                "Topic": b.topic, "Topic theme": b.topic_theme, "Angle": b.angle,
                "Hook (spoken)": b.hook_spoken, "Hook (text)": b.hook_text, "Hook (visual)": b.hook_visual,
                "Hook style": b.hook_style, "Story structure": f"{b.story_structure} — {b.structure_notes}",
                "Visual format": b.visual_format, "Key visuals": b.key_visuals,
                "Audio": b.audio_notes, "Audio type": b.audio_type, "Gap": b.gap,
                "Transcript": transcript, "Status": "analyzed",
            }
            bank.update(row["_row"], changes)
            done.append({**row, **changes})
        except Exception as e:  # noqa: BLE001
            ctx.error(f"analyze {row.get('Link')}", e)
            bank.update(row["_row"], {"Status": f"error: {str(e)[:200]}"})
        finally:
            if rid in tmpdirs:
                tmpdirs[rid].cleanup()
    bank.flush()
    return done


# ---------------------------------------------------------------------------------------
# Phase 8: remix picked outliers into the Script Queue
# ---------------------------------------------------------------------------------------

def whats_working_text(ctx: Ctx) -> str:
    rows = ctx.sheet.table("What's Working Now").rows()
    return "\n".join(f"{r['Category']} #{r['Rank']}: {r['Pattern']} ({r['Count']}x)" for r in rows)


def remix_picked(ctx: Ctx) -> list[dict]:
    bank = ctx.sheet.table("Outlier Bank")
    todo = [r for r in bank.rows(refresh=True) if truthy(r.get("Pick")) and r.get("Status") == "analyzed"]
    if not todo:
        return []
    ww = whats_working_text(ctx)
    queue = ctx.sheet.table("Script Queue")
    added = []
    plan_cols = {
        "Topic": ("Topic", "Topic plan"), "Angle": ("Angle", "Angle plan"), "Hook": ("Hook", "Hook plan"),
        "Story structure": ("Story structure", "Structure plan"), "Visual format": ("Visual format", "Format plan"),
        "Key visuals": ("Key visuals", "Visuals plan"), "Audio": ("Audio", "Audio plan"),
    }
    for row in todo:
        try:
            rx = ctx.ai.remix(outlier=row, whats_working=ww)
        except Exception as e:  # noqa: BLE001
            ctx.error(f"remix {row.get('Link')}", e)
            continue
        q = {"Reel ID": row["Reel ID"], "Added": fmt_date(ctx.now), "Source link": row.get("Link"),
             "Creator": row.get("Creator"), "Hook options": "\n".join(f"• {h}" for h in rx.hook_options),
             "Script outline": rx.script_outline, "Status": "to script"}
        for bp in rx.bricks:
            decision_col, plan_col = plan_cols[bp.brick]
            q[decision_col] = bp.decision
            q[plan_col] = bp.plan if bp.decision == "Remix" else f"(hold) {bp.original}"
        queue.append([q])
        bank.update(row["_row"], {"Status": "queued"})
        added.append(q)
    bank.flush()
    return added


# ---------------------------------------------------------------------------------------
# Phase 2: discovery
# ---------------------------------------------------------------------------------------

def discover(ctx: Ctx, max_new: int | None = None) -> list[dict]:
    s = ctx.settings
    keywords = s.list("seed_keywords")
    for kws in s.adjacent_niches().values():
        keywords += kws
    known = {clean_handle(r.get("Handle", "")) for r in ctx.sheet.table("Watch List").rows()}
    known |= {clean_handle(r.get("Handle", "")) for r in ctx.sheet.table("Candidates").rows()}

    found = ctx.scraper.search_reels(keywords, s.int("discovery_results_per_keyword"))
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # hits, best views
    for r in found:
        if r.owner in known:
            continue
        stats[r.owner][0] += 1
        stats[r.owner][1] = max(stats[r.owner][1], r.views or 0)
    ranked = sorted(stats, key=lambda h: (stats[h][0], stats[h][1]), reverse=True)[: s.int("discovery_max_profiles")]
    if not ranked:
        return []

    # tier gaps vs the 5 / 10 / 10 target
    counts = Counter(r.get("Tier", "?") for r in watched(ctx))
    gaps = {t: s.int(f"target_{t.lower()}") - counts.get(t, 0) for t in ("Big", "Mid", "Small")}

    cands = []
    for p in ctx.scraper.profiles(ranked):
        if p.is_private:
            continue
        ppw = scoring.posts_per_week(p.posts, ctx.now)
        dsp = scoring.days_since_last_post(p.posts, ctx.now)
        if ppw < s.float("min_posts_per_week") or dsp is None or dsp > s.float("max_days_since_post"):
            continue
        try:
            rel = ctx.ai.account_relevance(p.username, p.bio, [x.caption for x in p.posts])
        except Exception as e:  # noqa: BLE001
            ctx.error(f"account relevance @{p.username}", e)
            continue
        if rel.score < s.int("candidate_min_relevance"):
            continue
        t = scoring.tier(p.followers)
        cands.append({
            "Handle": p.username, "Link": p.url, "Followers": p.followers, "Tier": t, "Posts/week": ppw,
            "Days since post": dsp, "Relevance": rel.score, "Reason": rel.reason,
            "Source": f"keyword search ({stats[p.username][0]} hits)", "Found": fmt_date(ctx.now),
            "Approve": False, "Status": "new", "_gap": gaps.get(t, 0) > 0,
        })
    cands.sort(key=lambda c: (c["_gap"], c["Relevance"], c["Followers"] or 0), reverse=True)
    if max_new is not None:
        cands = cands[:max_new]
    for c in cands:
        c.pop("_gap")
    ctx.sheet.table("Candidates").append(cands)
    return cands


def tier_mix_html(ctx: Ctx) -> str:
    s = ctx.settings
    counts = Counter(r.get("Tier", "?") for r in watched(ctx))
    parts = [f"{t}: {counts.get(t, 0)}/{s.int('target_' + t.lower())}" for t in ("Big", "Mid", "Small")]
    return "<p>Watch list mix — " + " · ".join(parts) + f" (total {sum(counts.values())})</p>"


# ---------------------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------------------

BANK_COLS = ["Creator", "Outlier score", "Views", "Median", "Window", "Relevance", "Relevance reason", "Link"]


def run_daily(ctx: Ctx) -> None:
    promoted = promote_candidates(ctx)
    touched = fetch_watchlist_reels(ctx, ctx.settings.int("reels_per_check"))
    new = hunt(ctx, touched)
    analyzed = analyze_approved(ctx)
    queued = remix_picked(ctx)
    refresh_watch_stats(ctx)

    summary = f"{len(touched)} reels checked, {len(new)} new outliers, {len(analyzed)} analyzed, {len(queued)} queued"
    sections = [
        ("New outliers — tick Approve on the ones you find interesting", emailer.table(new, BANK_COLS, "Link")),
        ("Broken down into 7 bricks", emailer.table(
            analyzed, ["Creator", "Outlier score", "Topic", "Hook style", "Visual format", "Gap", "Link"], "Link")),
        ("Added to Script Queue", emailer.table(queued, ["Creator", "Hook", "Hook plan", "Source link"], "Source link")),
    ]
    if promoted:
        sections.insert(0, ("Added to watch list", "<p>" + ", ".join("@" + h for h in promoted) + "</p>"))
    if not watched(ctx):
        sections.insert(0, ("Your watch list is empty",
                            "<p>Run the <b>discover</b> workflow, then tick Approve in the Candidates tab.</p>"))
    ctx.email(f"Outliers {fmt_date(ctx.now)}: {len(new)} new, {len(analyzed)} analyzed", sections)
    ctx.log_run("ok" if not ctx.errors else "partial", summary)


def run_weekly(ctx: Ctx) -> None:
    """Phase 7: tally what repeats among this week's analyzed outliers."""
    bank = ctx.sheet.table("Outlier Bank")
    week_ago = ctx.now - timedelta(days=7)
    rows = [r for r in bank.rows(refresh=True)
            if r.get("Status") in ("analyzed", "queued")
            and (parse_time(r.get("Date found")) or ctx.now) >= week_ago]

    if rows:
        try:
            themes = ctx.ai.group_topics([f"{r.get('Topic theme')}: {r.get('Topic')}" for r in rows])
            for i, r in enumerate(rows):
                if themes.get(i):
                    r["Topic theme"] = themes[i]
                    bank.update(r["_row"], {"Topic theme": themes[i]})
            bank.flush()
        except Exception as e:  # noqa: BLE001
            ctx.error("topic grouping", e)

    categories = {
        "Topic": lambda r: r.get("Topic theme"),
        "Hook style": lambda r: r.get("Hook style"),
        "Story structure": lambda r: str(r.get("Story structure", "")).split(" — ")[0],
        "Visual format": lambda r: r.get("Visual format"),
        "Audio type": lambda r: r.get("Audio type"),
    }
    week_of = fmt_date(ctx.now - timedelta(days=6))
    ww, hist = [], []
    for cat, fn in categories.items():
        counter = Counter(v for v in (fn(r) for r in rows) if v)
        for rank, (pattern, count) in enumerate(counter.most_common(3), start=1):
            examples = [r.get("Link") for r in rows if fn(r) == pattern][:3]
            label = f"🔥 {pattern}" if count >= 3 else pattern
            ww.append({"Week of": week_of, "Category": cat, "Rank": rank, "Pattern": label, "Count": count,
                       "Examples": "\n".join(examples)})
            hist.append({"Week of": week_of, "Category": cat, "Rank": rank, "Pattern": pattern, "Count": count})
    if ww:
        ctx.sheet.table("What's Working Now").replace_all(ww)
        ctx.sheet.table("Pattern History").append(hist)

    # Keep growing the watch list until it hits the target size.
    s = ctx.settings
    target = s.int("target_big") + s.int("target_mid") + s.int("target_small")
    cands: list[dict] = []
    if len(watched(ctx)) < target:
        try:
            cands = discover(ctx)
        except Exception as e:  # noqa: BLE001
            ctx.error("discovery", e)

    pickable = [r for r in rows if r.get("Status") == "analyzed"]
    sections = [
        ("What's working now (🔥 = 3+ this week)", emailer.table(ww, ["Category", "Rank", "Pattern", "Count"])),
        ("This week's analyzed outliers — tick Pick on 3 to 5 for next week's videos",
         emailer.table(pickable, ["Creator", "Outlier score", "Topic", "Hook style", "Visual format", "Gap", "Link"], "Link")),
    ]
    if cands:
        sections.append(("New account candidates — tick Approve in the Candidates tab",
                         emailer.table(cands, ["Handle", "Followers", "Tier", "Posts/week", "Relevance", "Reason", "Link"], "Link")))
    sections.append(("Watch list", tier_mix_html(ctx)))
    ctx.email(f"Weekly pattern review {week_of}: {len(rows)} outliers", sections)
    ctx.log_run("ok" if not ctx.errors else "partial", f"{len(rows)} outliers reviewed, {len(cands)} candidates")


def run_monthly(ctx: Ctx) -> None:
    """Phase 9: deep baseline refresh, prune suggestions, fresh accounts, monthly report."""
    s = ctx.settings
    touched = fetch_watchlist_reels(ctx, s.int("monthly_refresh_reels"))
    profiles = {}
    try:
        profiles = {p.username: p for p in ctx.scraper.profiles([clean_handle(r["Handle"]) for r in watched(ctx)])}
    except Exception as e:  # noqa: BLE001
        ctx.error("follower refresh", e)
    refresh_watch_stats(ctx, profiles)

    wl = ctx.sheet.table("Watch List")
    flagged = []
    for row in watched(ctx):
        reasons = []
        last_post = parse_time(row.get("Last post"))
        if not last_post or (ctx.now - last_post).days > s.int("max_days_since_post"):
            reasons.append(f"no posts in {s.int('max_days_since_post')}+ days")
        added = parse_time(row.get("Added")) or ctx.now
        if (ctx.now - added).days >= 30 and int(num(row.get("Outliers (30d)")) or 0) == 0:
            reasons.append("no outliers in 30 days")
        if reasons:
            wl.update(row["_row"], {"Status": "drop?", "Notes": "; ".join(reasons)})
            flagged.append({"Handle": row["Handle"], "Why": "; ".join(reasons), "Link": row.get("Link")})
    wl.flush()

    cands = []
    try:
        cands = discover(ctx, max_new=s.int("monthly_new_accounts"))
    except Exception as e:  # noqa: BLE001
        ctx.error("discovery", e)

    # report
    month_ago = ctx.now - timedelta(days=30)
    bank = [r for r in ctx.sheet.table("Outlier Bank").rows(refresh=True)
            if (parse_time(r.get("Date found")) or month_ago) > month_ago]
    per = Counter(r.get("Creator") for r in bank)
    report = [{"Creator": c, "Outliers": n} for c, n in per.most_common()]
    runs = [r for r in ctx.sheet.table("Run Log").rows() if (parse_time(r.get("Time")) or month_ago) > month_ago]
    spend = sum(num(r.get("Total $")) or 0 for r in runs) + ctx.costs.total
    scanned = len(ctx.sheet.table("Reels").rows())
    sections = [
        ("Accounts flagged to drop — set Status to 'dropped' to remove, or back to 'active' to keep",
         emailer.table(flagged, ["Handle", "Why", "Link"], "Link")),
        ("New accounts suggested — tick Approve in the Candidates tab",
         emailer.table(cands, ["Handle", "Followers", "Tier", "Posts/week", "Relevance", "Reason", "Link"], "Link")),
        ("Outliers per creator (last 30 days)", emailer.table(report, ["Creator", "Outliers"])),
        ("Totals", f"<p>{len(bank)} outliers in 30 days · {scanned} reels tracked · "
                   f"estimated spend last 30 days ≈ ${spend:.2f}</p>{tier_mix_html(ctx)}"),
    ]
    ctx.email(f"Monthly maintenance {fmt_date(ctx.now)}", sections)
    ctx.log_run("ok" if not ctx.errors else "partial",
                f"{len(touched)} reels refreshed, {len(flagged)} flagged, {len(cands)} candidates")


def run_discover(ctx: Ctx) -> None:
    cands = discover(ctx)
    ctx.email(
        f"Discovery {fmt_date(ctx.now)}: {len(cands)} account candidates",
        [("Tick Approve in the Candidates tab for the ones to watch (aim ~5 big, 10 mid, 10 small)",
          emailer.table(cands, ["Handle", "Followers", "Tier", "Posts/week", "Relevance", "Reason", "Link"], "Link")),
         ("Watch list", tier_mix_html(ctx))],
    )
    ctx.log_run("ok" if not ctx.errors else "partial", f"{len(cands)} candidates")
