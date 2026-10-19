import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {key}")
    return value


UNIPILE_API_KEY = _require("UNIPILE_API_KEY")
UNIPILE_BASE_URL = os.getenv("UNIPILE_BASE_URL", "https://api2.unipile.com:13239/api/v1")
UNIPILE_ACCOUNT_ID = _require("UNIPILE_ACCOUNT_ID")

OPENAI_API_KEY = _require("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

GOOGLE_SHEETS_CREDENTIALS_FILE = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "service_account.json")
SPREADSHEET_ID = _require("SPREADSHEET_ID")
SHEET_NAME = os.getenv("SHEET_NAME", "Sheet1")

APIFY_API_TOKEN = _require("APIFY_API_TOKEN")
APIFY_ACTOR_ID = _require("APIFY_ACTOR_ID")

WAIT_BETWEEN_LEADS = int(os.getenv("WAIT_BETWEEN_LEADS", "45"))
WAIT_BEFORE_SEND = int(os.getenv("WAIT_BEFORE_SEND", "30"))

WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5000"))
