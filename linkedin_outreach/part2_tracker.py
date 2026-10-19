"""
Part 2 — LinkedIn Acceptance Tracker (webhook server)

Listens for Unipile events. When an invitation is accepted:
  1. Stringify the raw webhook body
  2. Use OpenAI to extract sender name, profile ID, and event type
  3. Call Apify to resolve the LinkedIn public username from the profile ID
  4. Mark "Request Accepted" = "Yes" in the sheet

Run:
    python part2_tracker.py

For production, run behind gunicorn:
    gunicorn part2_tracker:app --bind 0.0.0.0:5000

To expose locally for testing:
    ngrok http 5000   →  copy the URL into Unipile's Webhooks dashboard
"""
import json
import logging
import re

import requests
from flask import Flask, jsonify, request
from openai import OpenAI

import config
import sheets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

app = Flask(__name__)
openai_client = OpenAI(api_key=config.OPENAI_API_KEY)


# ---------------------------------------------------------------------------
# OpenAI: extract structured data from raw webhook body
# ---------------------------------------------------------------------------

def extract_acceptance_data(payload_str: str) -> dict:
    response = openai_client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a data extraction assistant. "
                    "Extract fields from webhook payloads and return valid JSON only — "
                    "no markdown fences, no explanation, just the JSON object."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Extract the following from this Unipile/LinkedIn webhook payload "
                    "and return as raw JSON:\n"
                    "- sender_name: full name of the person who accepted the invitation\n"
                    "- sender_profile_id: their LinkedIn provider_id or profile identifier\n"
                    "- event_type: the event type string from the payload\n\n"
                    f"Payload:\n{payload_str}\n\n"
                    'Return only: {"sender_name": "...", "sender_profile_id": "...", "event_type": "..."}'
                ),
            },
        ],
        max_tokens=200,
        temperature=0,
    )
    raw = response.choices[0].message.content.strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError(f"No JSON found in AI response: {raw}")
    return json.loads(match.group())


# ---------------------------------------------------------------------------
# Apify: resolve public username from profile ID
# ---------------------------------------------------------------------------

def get_username_from_apify(profile_id: str) -> str:
    profile_url = f"https://www.linkedin.com/in/{profile_id}"
    resp = requests.post(
        f"https://api.apify.com/v2/acts/{config.APIFY_ACTOR_ID}/run-sync-get-dataset-items",
        params={"token": config.APIFY_API_TOKEN},
        json={"profileUrls": [profile_url]},
        timeout=120,
    )
    resp.raise_for_status()

    items = resp.json()
    profile = items[0] if isinstance(items, list) and items else items

    username = (
        profile.get("publicIdentifier")
        or profile.get("public_identifier")
        or profile.get("username")
    )
    if not username:
        url = profile.get("profileUrl", "")
        if "/in/" in url:
            username = url.split("/in/")[-1].rstrip("/")

    if not username:
        raise ValueError(f"Could not find public identifier in Apify response: {profile}")
    return username.strip()


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

@app.route("/unipile-linkedin-webhook", methods=["POST"])
def webhook():
    try:
        body = request.get_json(force=True) or {}
        payload_str = json.dumps(body)
        log.info(f"Webhook received: {payload_str[:300]}…")

        data = extract_acceptance_data(payload_str)
        log.info(f"Extracted: {data}")

        sender_profile_id = str(data.get("sender_profile_id", "")).strip()
        if not sender_profile_id:
            log.warning("No sender_profile_id — skipping")
            return jsonify({"status": "skipped", "reason": "no profile id"}), 200

        username = get_username_from_apify(sender_profile_id)
        log.info(f"Resolved username: {username}")

        sheet = sheets.get_sheet()
        found = sheets.update_cell_by_username(sheet, username, "Request Accepted", "Yes")
        if found:
            log.info(f"Sheet updated: {username} → Request Accepted = Yes")
        else:
            log.warning(f"Username '{username}' not found in sheet")

        return jsonify({"status": "ok", "username": username}), 200

    except Exception as exc:
        log.exception(f"Error processing webhook: {exc}")
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info(f"Starting acceptance tracker on port {config.WEBHOOK_PORT}")
    app.run(host="0.0.0.0", port=config.WEBHOOK_PORT, debug=False)
