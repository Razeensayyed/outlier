"""Google Sheets as the database. Each tab is a Table with a fixed header row.

Values are written RAW so captions starting with "=" are never run as formulas and dates
stay in the ISO format the code reads back.
"""

from __future__ import annotations

import json
from typing import Any

import gspread
from gspread.utils import rowcol_to_a1

MAX_CELL = 45_000  # Sheets hard limit is 50k chars per cell

TABS: dict[str, list[str]] = {
    "Settings": ["Key", "Value", "Description"],
    "Watch List": [
        "Handle", "Platform", "Link", "Followers", "Tier", "Median views", "Engagement rate",
        "Sample size", "Confidence", "Posts/week", "Last post", "Last outlier", "Outliers (30d)",
        "Status", "Added", "Backfilled", "Last updated", "Notes",
    ],
    "Candidates": [
        "Handle", "Link", "Followers", "Tier", "Posts/week", "Days since post", "Relevance",
        "Reason", "Source", "Found", "Approve", "Status",
    ],
    "Reels": [
        "Reel ID", "Handle", "URL", "Posted", "Views", "Likes", "Comments", "Shares", "Duration",
        "Pinned", "Paid", "Coauthors", "Audio", "Caption", "Video URL", "First seen", "Last checked",
        "Score", "Status",
    ],
    "Outlier Bank": [
        "Reel ID", "Date found", "Link", "Creator", "Views", "Median", "Outlier score", "Window",
        "Real check", "Relevance", "Relevance reason", "Approve", "Status",
        "Topic", "Topic theme", "Angle", "Hook (spoken)", "Hook (text)", "Hook (visual)", "Hook style",
        "Story structure", "Visual format", "Key visuals", "Audio", "Audio type", "Gap",
        "Pick", "Transcript", "Caption",
    ],
    "What's Working Now": ["Week of", "Category", "Rank", "Pattern", "Count", "Examples"],
    "Pattern History": ["Week of", "Category", "Rank", "Pattern", "Count"],
    "Script Queue": [
        "Reel ID", "Added", "Source link", "Creator",
        "Topic", "Topic plan", "Angle", "Angle plan", "Hook", "Hook plan",
        "Story structure", "Structure plan", "Visual format", "Format plan",
        "Key visuals", "Visuals plan", "Audio", "Audio plan",
        "Hook options", "Script outline", "Status",
    ],
    "Run Log": [
        "Time", "Job", "Status", "Summary", "Apify items", "Apify $", "Claude $", "Groq $", "Total $",
        "Errors",
    ],
}

CHECKBOX_COLUMNS = {"Candidates": ["Approve"], "Outlier Bank": ["Approve", "Pick"]}


def truthy(v: Any) -> bool:
    return str(v).strip().lower() in {"true", "1", "yes", "y", "x", "✓", "✔"}


def _cell(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, (list, dict)):
        v = json.dumps(v, ensure_ascii=False)
    s = str(v)
    if len(s) > MAX_CELL:
        s = s[:MAX_CELL] + "…"
    return s


class Table:
    def __init__(self, ws: gspread.Worksheet, headers: list[str]):
        self.ws = ws
        self.headers = headers
        self._pending: list[dict] = []
        self._rows: list[dict] | None = None

    def rows(self, refresh: bool = False) -> list[dict]:
        """All data rows as dicts, each with a private `_row` (1-based sheet row number)."""
        if self._rows is None or refresh:
            values = self.ws.get_all_values()
            header = values[0] if values else self.headers
            self._rows = []
            for i, row in enumerate(values[1:], start=2):
                if not any(c.strip() for c in row):
                    continue
                d = {h: (row[j] if j < len(row) else "") for j, h in enumerate(header)}
                d["_row"] = i
                self._rows.append(d)
        return self._rows

    def append(self, records: list[dict]) -> None:
        if not records:
            return
        values = [[_cell(r.get(h)) for h in self.headers] for r in records]
        self.ws.append_rows(values, value_input_option="RAW", table_range="A1")
        self._rows = None

    def update(self, row: int, changes: dict) -> None:
        """Queue cell updates for one row; call flush() to send them in one request."""
        for key, val in changes.items():
            if key not in self.headers:
                continue
            col = self.headers.index(key) + 1
            self._pending.append({"range": rowcol_to_a1(row, col), "values": [[_cell(val)]]})

    def flush(self) -> None:
        if self._pending:
            for i in range(0, len(self._pending), 500):
                self.ws.batch_update(self._pending[i:i + 500], value_input_option="RAW")
            self._pending = []
            self._rows = None

    def replace_all(self, records: list[dict]) -> None:
        self.ws.batch_clear([f"A2:{rowcol_to_a1(max(self.ws.row_count, 2), len(self.headers))}"])
        self.append(records)


class Sheet:
    def __init__(self, service_account_json: str, sheet_id: str):
        info = json.loads(service_account_json)
        self.client = gspread.service_account_from_dict(info)
        self.book = self.client.open_by_key(sheet_id)
        self._tables: dict[str, Table] = {}

    @property
    def url(self) -> str:
        return self.book.url

    def table(self, name: str) -> Table:
        if name not in self._tables:
            try:
                ws = self.book.worksheet(name)
            except gspread.WorksheetNotFound:
                ws = self._create(name)
            # Use the sheet's real header row so reordered/extra columns you add are respected.
            self._tables[name] = Table(ws, ws.row_values(1) or TABS[name])
        return self._tables[name]

    def _create(self, name: str) -> gspread.Worksheet:
        headers = TABS[name]
        ws = self.book.add_worksheet(title=name, rows=1000, cols=max(len(headers), 5))
        ws.update(range_name="A1", values=[headers])
        ws.freeze(rows=1)
        ws.format(f"A1:{rowcol_to_a1(1, len(headers))}", {"textFormat": {"bold": True}})
        return ws

    def ensure_all(self) -> None:
        """Create missing tabs, add any missing header columns, and set up checkbox columns."""
        for name, headers in TABS.items():
            t = self.table(name)
            current = t.headers
            missing = [h for h in headers if h not in current]
            if missing:
                merged = current + missing
                if len(merged) > t.ws.col_count:
                    t.ws.add_cols(len(merged) - t.ws.col_count)
                t.ws.update(range_name="A1", values=[merged])
                t.headers = merged
        requests = []
        for name, cols in CHECKBOX_COLUMNS.items():
            t = self.table(name)
            for col in cols:
                idx = t.headers.index(col)
                requests.append({
                    "setDataValidation": {
                        "range": {
                            "sheetId": t.ws.id, "startRowIndex": 1, "endRowIndex": t.ws.row_count,
                            "startColumnIndex": idx, "endColumnIndex": idx + 1,
                        },
                        "rule": {"condition": {"type": "BOOLEAN"}},
                    }
                })
        if requests:
            self.book.batch_update({"requests": requests})
        # Remove the default empty "Sheet1" if it's still there.
        try:
            s1 = self.book.worksheet("Sheet1")
            if not any(any(c for c in r) for r in s1.get_all_values()):
                self.book.del_worksheet(s1)
        except gspread.WorksheetNotFound:
            pass
