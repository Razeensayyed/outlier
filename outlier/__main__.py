"""Usage: python -m outlier {init,check,discover,daily,weekly,monthly} [--username HANDLE]"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

from . import jobs
from .instagram import normalize_profile, normalize_reel


def cmd_init(ctx: jobs.Ctx) -> None:
    print(f"Sheet ready: {ctx.sheet.url}")
    print("Tabs created and Settings seeded. Edit the Settings tab (niche, keywords) before the first discover run.")


def cmd_check(ctx: jobs.Ctx, username: str) -> None:
    """Smoke-test every integration with tiny requests (a few cents at most)."""
    ok = True

    def step(name, fn):
        nonlocal ok
        try:
            print(f"✔ {name}: {fn()}")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"✘ {name}: {type(e).__name__}: {e}")

    step("Google Sheet", lambda: ctx.sheet.url)
    step("ffmpeg", lambda: subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True).stdout.split("\n")[0])

    def reels():
        items = ctx.scraper._run("reel_actor", {"usernames": [username], "limit": 3}, max_items=5)
        if not items:
            raise RuntimeError(f"{ctx.settings.str('reel_actor')} returned 0 items - check reel_actor_input in Settings")
        r = normalize_reel(items[0], username)
        return (f"{len(items)} items; first: {r.url} views={r.views} likes={r.likes} posted={r.posted_at} "
                f"pinned={r.pinned} audio={r.audio!r}; missing={r.missing_fields()}; raw keys={r.raw_keys}")

    def search():
        items = ctx.scraper._run("search_actor", {"keywords": ctx.settings.list("seed_keywords")[:1], "limit": 5}, max_items=5)
        if not items:
            raise RuntimeError(f"{ctx.settings.str('search_actor')} returned 0 items - check search_actor_input")
        r = normalize_reel(items[0])
        return f"{len(items)} items; first owner=@{r.owner} views={r.views}; raw keys={r.raw_keys}"

    def profile():
        items = ctx.scraper._run("profile_actor", {"usernames": [username]}, max_items=2)
        if not items:
            raise RuntimeError("profile actor returned 0 items - check profile_actor_input")
        p = normalize_profile(items[0])
        return f"@{p.username} followers={p.followers} latest posts={len(p.posts)}"

    step(f"Reel scraper ({ctx.settings.str('reel_actor')})", reels)
    step(f"Search scraper ({ctx.settings.str('search_actor')})", search)
    step(f"Profile scraper ({ctx.settings.str('profile_actor')})", profile)
    step("Claude", lambda: ctx.ai.reel_relevance(username, "5 ChatGPT prompts for small business owners", "").model_dump())

    def groq():
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "tone.mp3"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                            str(a)], check=True)
            return f"ok ({ctx.stt.transcribe(a, 2)!r})"

    step("Groq Whisper", groq)
    step("Email", lambda: (ctx.email("Outlier setup check", [("It works", "<p>Your pipeline can send email.</p>")]), "sent")[1])
    ctx.log_run("ok" if ok else "failed", "setup check")
    if not ok:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="outlier")
    parser.add_argument("job", choices=["init", "check", "discover", "daily", "weekly", "monthly"])
    parser.add_argument("--username", default="garyvee", help="Instagram handle used by `check`")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    ctx = jobs.Ctx(args.job)
    try:
        {
            "init": lambda: cmd_init(ctx),
            "check": lambda: cmd_check(ctx, args.username),
            "discover": lambda: jobs.run_discover(ctx),
            "daily": lambda: jobs.run_daily(ctx),
            "weekly": lambda: jobs.run_weekly(ctx),
            "monthly": lambda: jobs.run_monthly(ctx),
        }[args.job]()
    except Exception as e:  # noqa: BLE001
        ctx.error(args.job, e)
        traceback.print_exc()
        try:
            ctx.log_run("failed", str(e)[:500])
            ctx.email(f"Outlier {args.job} run FAILED", [("Error", f"<pre>{traceback.format_exc()[-3000:]}</pre>")])
        finally:
            sys.exit(1)
    if ctx.errors:
        print("Finished with problems:\n" + "\n".join(ctx.errors))


if __name__ == "__main__":
    main()
