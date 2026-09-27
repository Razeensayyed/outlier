# Outlier Finder (Instagram)

Your manual 9-phase outlier research process, automated. Every morning it checks your watch list, flags reels that did **5x+ the creator's median**, filters out paid, boosted and off-niche reels, and emails you the list. The reels you approve get broken into the **7 bricks** by Claude. The ones you pick get **Hold/Remix** plans in your Script Queue.

Everything lives in one Google Sheet, runs free on GitHub Actions, and costs roughly **$10–20/month** in API usage (see [Costs](#costs)).

| Phase | What happens | Who |
|---|---|---|
| 1 Niche | `Settings` tab: niche statement, keywords, adjacent niches, thresholds | You (edit any time) |
| 2 Watch list | Keyword search → qualify (posts weekly, active in 30 days, AI relevance) → `Candidates` tab | Auto, **you tick Approve** |
| 3 Baselines | Median views of the last 20 eligible reels (≥7 days old, no pinned/paid/boosted) | Auto, daily + deep refresh monthly |
| 4 Hunt | Score = views ÷ median; flag ≥5x; trend (≤14d) / evergreen (≤180d); reels under 48h wait | Auto, daily |
| 5 Validate | Real? (paid, giveaway, engagement vs views) + Relevant? (AI on caption + Hinglish transcript) | Auto. **Interesting? = you tick Approve** |
| 6 Outlier Bank | Frames + transcript → Claude → Topic, Angle, Hook (spoken/text/visual), Structure, Format, Visuals, Audio, **Gap** | Auto, for approved rows |
| 7 Weekly review | Sunday: tally what repeats → `What's Working Now` (top 3 per category, 🔥 = 3+) | Auto |
| 8 Pick & remix | **You tick Pick** on 3–5 → Claude marks each brick Hold/Remix, 3 hook options, script outline → `Script Queue` | You pick, AI plans |
| 9 Maintain | Monthly: refresh baselines and followers, flag dead accounts as `drop?`, suggest 5 new ones, report | Auto, **you confirm drops** |

**Your time:** about 5 minutes a day (tick Approve in the email/sheet) and 10 minutes on Sunday (tick Pick).

---

## Setup (about 30 minutes, one time)

### 1. Google Sheet + service account
1. Create an empty Google Sheet. Copy its ID from the URL: `docs.google.com/spreadsheets/d/`**`THIS_PART`**`/edit`.
2. Go to [console.cloud.google.com](https://console.cloud.google.com). Create a project, then go to **APIs & Services → Enable APIs** and enable **Google Sheets API**.
3. Go to **IAM & Admin → Service Accounts → Create**. Any name works and it needs no roles. Open it, then **Keys → Add key → JSON**. A `.json` file downloads.
4. Share your Sheet with the service account's email (`…@….iam.gserviceaccount.com`) as **Editor**.

### 2. API keys
| Service | Where | Notes |
|---|---|---|
| Apify | [console.apify.com](https://console.apify.com) → Settings → API & Integrations | The free plan includes $5/month |
| Anthropic (Claude) | [console.anthropic.com](https://console.anthropic.com) → API Keys | Add prepaid credits (e.g. $10) and set a monthly limit |
| Groq (Whisper) | [console.groq.com](https://console.groq.com/keys) | Has a free tier |
| Gmail App Password | [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) | Needs 2-Step Verification turned on |

### 3. GitHub secrets
In this repo, go to **Settings → Secrets and variables → Actions → New repository secret** and add:

| Secret | Value |
|---|---|
| `APIFY_TOKEN` | Apify API token |
| `ANTHROPIC_API_KEY` | Claude API key |
| `GROQ_API_KEY` | Groq API key |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | The **entire contents** of the downloaded `.json` file |
| `SHEET_ID` | The Sheet ID from step 1 |
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | The 16-character app password |
| `EMAIL_TO` | (optional) Where to send digests. Defaults to `GMAIL_ADDRESS` |

### 4. First run
Go to **Actions → Outlier finder → Run workflow** and run these jobs in order:

1. **`init`** creates all the tabs and fills `Settings` with defaults. Then open the Sheet and edit `niche_statement`, `seed_keywords` and `adjacent_niches`.
2. **`check`** tests every connection with tiny requests and sends you a test email. Read the log:
   - If a scraper line shows ✘ or `returned 0 items`, open that actor's page on apify.com, click **Input → JSON**, and copy its field names into `reel_actor_input` / `search_actor_input` in Settings. Keep the `{{usernames}}`, `{{keywords}}` and `{{limit}}` placeholders. The log prints the `raw keys` each actor returns, and the code already understands the common field names.
   - If the cheap actors keep failing, switch `reel_actor` to `apify/instagram-reel-scraper` with input `{"username": "{{usernames}}", "resultsLimit": "{{limit}}"}`. It's more reliable but costs about $1 per 1,000 reels.
3. **`discover`** finds accounts from your keywords and emails you the list. In `Candidates`, tick **Approve** on 20–30 of them (aim for about 5 big, 10 mid, 10 small). You can also type handles straight into the `Watch List` tab.
4. After that, it runs on its own: **daily at 07:07 IST, Sunday review at 08:43 IST, monthly on the 1st**. To change the times, edit the cron lines in `.github/workflows/outlier.yml` (they're in UTC).

The first daily run backfills about 40 reels per new account, so its email will have more outliers than usual.

---

## Your routine

- **Daily email:** open the Sheet → `Outlier Bank` → tick **Approve** on the reels you find interesting. The next run breaks them down.
- **Sunday email:** read `What's Working Now`, then tick **Pick** on 3–5 analyzed outliers. The next run writes their Hold/Remix plans into `Script Queue`.
- **Monthly email:** for accounts flagged `drop?`, set Status to `dropped` or back to `active`. Approve any new candidates.

## Tabs

| Tab | Contents |
|---|---|
| Settings | Every knob (threshold, windows, actor IDs, models). Edits apply on the next run |
| Watch List | Creator, Platform, Link, Followers, Tier, Median views, Engagement rate, Posts/week, Last post, Outliers (30d), Status |
| Candidates | Discovered accounts waiting for your Approve |
| Reels | Every reel seen, with its latest views and score. Rejections show the reason (`rejected: paid partnership`, `off-niche`, `suspect boost`) |
| Outlier Bank | Validated outliers + the 7 bricks + Gap + transcript. Approve and Pick checkboxes |
| What's Working Now | This week's top 3 per category |
| Pattern History | Every week's top 3, to spot rising and fading patterns |
| Script Queue | Hold/Remix decision + plan per brick, hook options, script outline |
| Run Log | Every run's summary, errors and estimated cost |

## Costs

With 25 accounts checked daily, about 60 AI breakdowns a month, and cheap third-party scrapers:

| Item | Est. / month |
|---|---|
| Apify: daily checks (~9K reel reads at ~$0.35–0.50 per 1K), discovery, profiles | $4–8. The free $5 covers most of it. Add a card for overage, or cut `reels_per_check` |
| Claude Sonnet 5: breakdowns (~$0.03 each) + remixes + weekly review. Haiku 4.5: relevance checks | $3–8 |
| Groq Whisper large-v3 | < $1 |
| GitHub Actions, Google Sheets, Gmail | $0 |
| **Total** | **≈ $10–20** |

Every run writes its estimated cost to `Run Log`, and the monthly email shows the 30-day total. To spend less: lower `reels_per_check` or `max_analyses_per_run`, or set `analysis_model` to `claude-haiku-4-5`.

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest -q                 # offline tests (fake sheet, scraper and AI)
python -m outlier daily             # needs the env vars above
```

Code map: `outlier/jobs.py` (the phases), `scoring.py` (median, score, validation math), `instagram.py` (normalizes different scrapers' JSON), `scraper.py` (Apify), `ai.py` (Claude prompts + fixed taxonomies), `media.py` (ffmpeg), `transcribe.py` (Groq), `sheets.py` (Google Sheets), `emailer.py`.

Scraping Instagram breaks Meta's terms of service. The scrapers only use public data and never log in with your account.
