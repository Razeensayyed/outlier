"""
Part 1 — LinkedIn Outreach Sender

For each lead in the sheet where "LinkedIn Connection Request" is blank:
  1. Fetch their Unipile profile
  2. Skip if already connected or invite pending
  3. Pull their 3 most recent posts
  4. Generate a personalised <300-char connection note via OpenAI
  5. Send the invite via Unipile
  6. Mark the row "Yes" in the sheet

Run manually:  python part1_sender.py
Schedule:      add to cron, e.g. twice a day at 8 AM and 6 PM
"""
import logging
import time

import requests
from openai import OpenAI

import config
import sheets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

_HEADERS = {
    "X-API-KEY": config.UNIPILE_API_KEY,
    "Content-Type": "application/json",
    "Accept": "application/json",
}
openai_client = OpenAI(api_key=config.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# Unipile helpers
# ---------------------------------------------------------------------------

def get_profile(username: str) -> dict:
    resp = requests.get(
        f"{config.UNIPILE_BASE_URL}/users/{username}",
        headers=_HEADERS,
        params={"account_id": config.UNIPILE_ACCOUNT_ID},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_recent_posts(provider_id: str, limit: int = 3) -> list[str]:
    resp = requests.get(
        f"{config.UNIPILE_BASE_URL}/users/{provider_id}/posts",
        headers=_HEADERS,
        params={"account_id": config.UNIPILE_ACCOUNT_ID, "limit": limit},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items", data if isinstance(data, list) else [])
    texts = []
    for post in items[:limit]:
        text = post.get("text") or post.get("content") or post.get("description") or ""
        if text.strip():
            texts.append(text.strip())
    return texts


def send_invite(provider_id: str, message: str) -> dict:
    resp = requests.post(
        f"{config.UNIPILE_BASE_URL}/users/invite",
        headers=_HEADERS,
        json={
            "provider_id": provider_id,
            "account_id": config.UNIPILE_ACCOUNT_ID,
            "message": message,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# OpenAI helper
# ---------------------------------------------------------------------------

def write_connection_note(first_name: str, last_name: str, posts: list[str]) -> str:
    posts_text = "\n---\n".join(posts) if posts else "No recent posts available."
    response = openai_client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert copywriter who writes short, genuine LinkedIn connection request notes.\n"
                    "Rules:\n"
                    "- Under 300 characters total (LinkedIn's hard limit)\n"
                    "- Never use generic openers like 'I came across your profile'\n"
                    "- Reference something specific from their recent posts to show you read their content\n"
                    "- Sound human, warm, and conversational — not like a bot\n"
                    "Return ONLY the message text, no quotes, no labels, no extra formatting."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Write a LinkedIn connection note for {first_name} {last_name}.\n\n"
                    f"Their recent posts:\n{posts_text}\n\n"
                    "Write ONE personalized note under 300 characters. Return only the message."
                ),
            },
        ],
        max_tokens=100,
        temperature=0.8,
    )
    return response.choices[0].message.content.strip()[:300]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run():
    log.info("Starting LinkedIn outreach sender")
    sheet = sheets.get_sheet()
    records = sheet.get_all_records()

    new_leads = [
        (i + 2, row)
        for i, row in enumerate(records)
        if not str(row.get("LinkedIn Connection Request", "")).strip()
    ]
    log.info(f"Found {len(new_leads)} new lead(s) to process")

    for row_num, lead in new_leads:
        username = str(lead.get("Username", "")).strip()
        first_name = str(lead.get("First Name", "")).strip()
        last_name = str(lead.get("Last Name", "")).strip()

        if not username:
            log.warning(f"Row {row_num}: no Username — skipping")
            continue

        log.info(f"── {first_name} {last_name} (@{username})")

        # 1. Fetch profile
        try:
            profile = get_profile(username)
        except requests.HTTPError as exc:
            log.error(f"  Profile fetch failed: {exc}")
            time.sleep(config.WAIT_BETWEEN_LEADS)
            continue

        # 2. Check existing relationship
        already_connected = bool(profile.get("is_relation"))
        invite_pending = profile.get("relation_request_state", "") == "pending"

        if already_connected or invite_pending:
            reason = "already connected" if already_connected else "invite already pending"
            log.info(f"  Skipping — {reason}")
            sheets.update_cell_by_username(sheet, username, "LinkedIn Connection Request", "sent")
            time.sleep(config.WAIT_BETWEEN_LEADS)
            continue

        provider_id = profile.get("provider_id", "")
        if not provider_id:
            log.error("  No provider_id in profile response — skipping")
            continue

        # 3. Fetch recent posts
        posts = get_recent_posts(provider_id)
        log.info(f"  Got {len(posts)} post(s)")

        # 4. Generate message
        message = write_connection_note(first_name, last_name, posts)
        log.info(f"  Message ({len(message)} chars): {message}")

        # 5. Wait then send
        log.info(f"  Waiting {config.WAIT_BEFORE_SEND}s before sending…")
        time.sleep(config.WAIT_BEFORE_SEND)

        try:
            send_invite(provider_id, message)
            log.info("  Invite sent ✓")
            sheets.update_cell_by_username(sheet, username, "LinkedIn Connection Request", "Yes")
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else ""
            log.error(f"  Send invite failed: {exc} — {body}")

        log.info(f"  Waiting {config.WAIT_BETWEEN_LEADS}s before next lead…")
        time.sleep(config.WAIT_BETWEEN_LEADS)

    log.info("Done.")


if __name__ == "__main__":
    run()
