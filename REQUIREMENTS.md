# Outlier Finder: Automation Requirements

These requirements turn the manual 9-phase outlier workflow into a pipeline that runs on a schedule.
The goal is to automate the collection, math, logging and pattern-counting steps. Judgment calls stay with you: whether an idea is interesting, and which ideas to pick and remix.

---

## 0. Decisions to make first

| Decision | Options | Recommendation |
|---|---|---|
| Platforms | Instagram, TikTok, YouTube Shorts | Start with **one** (probably Instagram), then add the others |
| Build style | No-code (n8n / Make + Apify + Sheets), or code (Python + database) | n8n + Apify + Google Sheets for a v1. Move to code once it grows past about 50 accounts |
| Where data lives | Google Sheets, Airtable, Notion, Postgres/Supabase | Google Sheets is fine for v1 because it matches your current setup |
| Monthly budget | About $20–$80/mo covers scraping and AI for 20–30 accounts checked daily | Set a hard spending cap in each tool |
| How results reach you | Email, Telegram, Slack, or just the sheet | A daily digest message with links |

---

## 1. Data access (the hardest part)

Official APIs **do not** give you view counts on other people's short-form videos, except on YouTube.

| Platform | Official API | What you actually need |
|---|---|---|
| **YouTube Shorts** | YouTube Data API v3 works: `search.list`, `playlistItems.list`, `videos.list` (viewCount, likeCount, commentCount, duration). Free, with a quota of 10,000 units/day | A Google Cloud project and an API key. Shorts have no official flag, so detect them by duration (≤ 180 s) or by the `/shorts/` URL |
| **Instagram** | The Graph API's Business Discovery endpoint returns followers and like/comment counts for other Business/Creator accounts, but **no reel play counts** | A third-party scraper that returns `videoPlayCount`, `isPinned`, paid-partnership flag, audio info and caption (for example Apify's Instagram Reel/Profile scrapers) |
| **TikTok** | The Research API is limited to academics. The Display API only covers your own account | A third-party scraper (for example Apify's TikTok scrapers, or a paid data API) that returns `playCount`, `shareCount`, `isPinned`, `musicMeta` and `isAd` |

**Requirements**
- R1.1 Scraper account and API token (Apify or equivalent), with pay-per-result pricing and a spending limit.
- R1.2 YouTube Data API key.
- R1.3 Each reel record must include: platform, reel ID, URL, creator handle, posted_at, views, likes, comments, shares (if available), duration, caption, pinned flag, paid-partnership/ad flag, audio name/ID, thumbnail URL, and video URL (for download).
- R1.4 Each creator record must include: handle, platform, follower count, and last post date.
- R1.5 Accept the risk: scraping public data breaches Meta's and TikTok's terms. Never log the scraper in with your own creator account, and use the provider's proxies.

---

## 2. Phase 1: Niche config (one-time, manual input)

- R2.1 A config file or sheet tab called `Niche` with:
  - Your one-line niche statement.
  - 10–15 seed keywords and hashtags.
  - 2–3 adjacent niches, each with its own keywords.
  - Outlier threshold (default **5x**, can be set to 3x).
  - Time window: `trend` = 14 days, `evergreen` = 180 days.
- R2.2 The AI steps use this config to judge relevance, so the niche statement must be specific.

---

## 3. Phase 2: Watch list discovery (semi-automated)

| Manual method | Can it be automated? |
|---|---|
| Keyword search → top videos | **Yes.** YouTube via `search.list`. IG and TikTok via hashtag or keyword scrapers |
| Who top creators follow | **Partly.** Following-list scrapers exist but are unreliable and often blocked |
| "Suggested for you" | **No.** This is personalized to your logged-in account. Keep it manual |
| Commenters who are creators | **Yes.** Scrape comments on top posts, then keep commenters above a follower threshold who post video |

- R3.1 A weekly job runs keyword searches and collects candidate creators into a `Candidates` tab.
- R3.2 Qualification is automatic: a candidate is kept only if it has ≥ 1 short video per week over the last 4 weeks, a post in the last 30 days, and an AI relevance score ≥ threshold against your niche statement (based on bio plus recent captions).
- R3.3 Each candidate gets a size tier: Big (500K+), Mid (50K–500K), Small (<50K). The job reports the tier mix against your 5/10/10 target.
- R3.4 **You approve** each candidate before it goes on the watch list. A checkbox column is enough.

---

## 4. Phase 3: Baselines (automated, monthly or rolling)

- R4.1 For each account, fetch the last 20–25 reels and remove pinned reels, paid collabs or ads, and suspected boosts (see R6.2).
- R4.2 Median views = the median of the most recent 15–20 remaining reels. If fewer than 10 remain, mark the baseline as `low confidence`.
- R4.3 **Age rule:** only count reels at least 7 days old in the baseline. Views keep growing after posting, so newer reels would drag the median down.
- R4.4 Write the results to the `Watch List` tab: Creator, Platform, Link, Followers, Median views, Sample size, Last updated.
- R4.5 The baseline must **not** include the reel being scored.

---

## 5. Phase 4: Outlier detection (automated, daily)

- R5.1 Scheduled daily run (cron, GitHub Actions, or an n8n schedule trigger) that fetches new reels for every watched account.
- R5.2 Outlier score = `views / creator_median`. Flag reels where score ≥ threshold (5x, or 3x for small niches).
- R5.3 **Minimum age:** don't score reels younger than 48 hours. Store their view counts and re-score them later.
- R5.4 Keep only reels inside the time window from R2.1 (trend or evergreen).
- R5.5 Remove duplicates by reel ID so the same reel isn't logged twice.
- R5.6 Store a daily snapshot of views per reel. This lets you see how fast each reel is growing.

---

## 6. Phase 5: Validation (mostly automated, one human check)

- R6.1 **Real? (automated)** Reject reels that are marked paid partnership or ad, or whose caption contains giveaway or #ad terms.
- R6.2 **Proportional engagement (automated):** compute `(likes + comments + shares) / views` for the flagged reel and compare it with the creator's typical ratio. If it's far below normal (for example under 0.3x), the reel was probably boosted, so reject it or mark it `suspect`.
- R6.3 **Relevant? (AI)** An LLM scores caption plus transcript against your niche statement, returning a score from 0 to 10 with a one-line reason.
- R6.4 **Interesting? (human)** The digest shows each surviving outlier with 👍/👎 buttons or a checkbox column. Only 👍 items move on to the brick analysis, which saves AI costs.

---

## 7. Phase 6: Outlier Bank with 7-brick breakdown (automated)

Pipeline for each approved outlier:
1. **Download** the video file using the scraper's video URL.
2. **Transcribe** the audio with a speech-to-text API (for example OpenAI Whisper, Deepgram or AssemblyAI) to get the spoken hook and script.
3. **Extract frames** with ffmpeg: the first 3 seconds at 2–4 fps, then 1 frame every 2–3 seconds after that. These capture the visual hook, the on-screen text and the format.
4. **Analyze** with a multimodal LLM (for example Claude), giving it frames, transcript, caption, audio metadata and your niche. It returns structured JSON with:
   - Topic, Angle
   - Hook (spoken, text-on-screen, and visual as separate fields)
   - Story structure
   - Visual format (for example talking head, green screen, screen recording, or B-roll plus voiceover)
   - Key visuals
   - Audio (trending sound name, or original voice with music mood)
   - **Gap**: what the reel did weakly that you could do better
5. **Write a row** to the `Outlier Bank` tab: Date found, Link, Creator, Views, Outlier score, the 7 bricks, Gap, and Status.

Requirements:
- R7.1 Storage for downloaded videos. They can be temporary and deleted after analysis.
- R7.2 **A fixed taxonomy** (a list of allowed values) for Hook style, Story structure, Visual format and Audio type. Without one, the AI will name the same thing in many different ways, and Phase 7 counts won't work.
- R7.3 An LLM API key, plus a speech-to-text API key or a self-hosted Whisper model.

---

## 8. Phase 7: Weekly pattern review (automated, every Sunday)

- R8.1 A Sunday job reads the week's Outlier Bank rows and counts Topics, Hook styles, Formats, Structures and Audio types.
- R8.2 Topics are free text, so the AI groups them into themes before counting.
- R8.3 Writes the **"What's Working Now"** block: the top 3 in each category, with counts and example links. Items that appeared 3+ times are highlighted.
- R8.4 Keeps a week-over-week history so you can see which patterns are rising and which are fading.

---

## 9. Phase 8: Pick and remix (human decision, AI assist)

- R9.1 **You** pick 3–5 outliers each week using a `Pick` checkbox.
- R9.2 For each pick, the AI proposes **Hold/Remix** for each of the 7 bricks. It uses this week's "What's Working Now" patterns and your niche, and gives 2–3 alternative angles and hooks for each brick marked Remix.
- R9.3 You confirm or edit, then the item moves to a `Script Queue` tab or tool (Sheets, Notion or Trello). An optional step has the AI draft a first script from the chosen bricks.

---

## 10. Phase 9: Maintenance (automated, monthly)

- R10.1 Recalculates every baseline (Phase 3).
- R10.2 Marks an account for removal if it has posted nothing in 30 days, or had 0 outliers in 30 days. **You confirm** before it's dropped.
- R10.3 Runs discovery (Phase 2) and suggests 3–5 new accounts, prioritizing whichever size tier is short.
- R10.4 Monthly report: outliers found per account, hit rate, and API and AI spend.

---

## 11. Infrastructure and non-functional requirements

- **Scheduler**: daily (Phase 4–6), weekly (Phase 2 discovery and Phase 7), monthly (Phase 9).
- **Orchestrator**: n8n (self-hosted or cloud) or Make, or Python scripts on GitHub Actions or a small VPS.
- **Secrets**: scraper token, YouTube key, LLM key, speech-to-text key, and Google service account. Store them in the tool's credential store, never in the sheet.
- **Database / sheet tabs**: `Niche`, `Watch List`, `Candidates`, `Reels` (raw plus daily snapshots), `Outlier Bank`, `What's Working Now`, `Script Queue`, `Run Log`.
- **Reliability**: retry failed scrapes, log every run, and alert you if a run fails or returns 0 results. A result of 0 usually means the scraper broke.
- **Cost controls**: fetch only new reels per account per day (not all reels), run AI analysis only after your 👍, and keep spending caps on every paid API.
- **Rough daily volume**: 25 accounts × about 1–3 new reels = 25–75 reels scored per day, with maybe 1–5 outliers going to AI analysis.

---

## 12. What stays manual (by design)

1. Writing the niche statement and keywords (Phase 1).
2. Approving new accounts and removals.
3. The "Interesting?" check (a 👍/👎 in the digest).
4. Picking the week's 3–5 outliers and signing off on Hold/Remix choices.

That comes to roughly **5 minutes a day plus 15 minutes a week**, down from about 3–4 hours a week.

---

## Minimum shopping list (v1)

- [ ] Google account + Google Sheet + service account (for writing to the sheet)
- [ ] Apify account (or similar) for Instagram / TikTok data
- [ ] YouTube Data API key (if you use Shorts)
- [ ] LLM API key (Claude) for relevance, the 7-brick analysis, pattern grouping and remix suggestions
- [ ] Speech-to-text API key (or Whisper)
- [ ] ffmpeg (for frame extraction) wherever the pipeline runs
- [ ] n8n / Make account, or a place to run Python on a schedule (GitHub Actions or a VPS)
- [ ] A notification channel (Telegram bot, Slack webhook, or email)
