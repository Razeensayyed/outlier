"""Apify wrapper. Actor IDs and input templates come from the Settings tab."""

from __future__ import annotations

import copy
import logging
from datetime import timedelta
from typing import Any

from apify_client import ApifyClient

from .costs import Costs
from .instagram import Profile, Reel, normalize_profile, normalize_reel
from .settings import Settings

log = logging.getLogger(__name__)


def fill_template(template: Any, values: dict[str, Any]) -> Any:
    """Replace "{{name}}" placeholders anywhere in a JSON-like structure.

    A string that is exactly "{{name}}" is replaced by the value itself (so lists stay
    lists and numbers stay numbers); placeholders inside longer strings are substituted
    as text.
    """
    if isinstance(template, dict):
        return {k: fill_template(v, values) for k, v in template.items()}
    if isinstance(template, list):
        return [fill_template(v, values) for v in template]
    if isinstance(template, str):
        for name, val in values.items():
            token = "{{" + name + "}}"
            if template == token:
                return copy.deepcopy(val)
            if token in template:
                template = template.replace(token, str(val))
        return template
    return template


class Scraper:
    def __init__(self, token: str, settings: Settings, costs: Costs):
        self.client = ApifyClient(token)
        self.s = settings
        self.costs = costs

    def _run(self, actor_key: str, values: dict[str, Any], max_items: int | None = None) -> list[dict]:
        actor = self.s.str(actor_key)
        run_input = fill_template(self.s.json(f"{actor_key}_input"), values)
        log.info("Apify %s input=%s", actor, run_input)
        run = self.client.actor(actor).call(
            run_input=run_input,
            max_items=max_items,
            run_timeout=timedelta(minutes=30),
        )
        if run is None:
            raise RuntimeError(f"Apify actor {actor} did not return a run")
        items = list(self.client.dataset(run.default_dataset_id).iterate_items())
        # Some actors return an error object instead of data rows.
        items = [i for i in items if isinstance(i, dict) and not (set(i) <= {"error", "errorDescription", "url"})]
        status = str(run.status).upper()
        if status != "SUCCEEDED":
            if not items:
                raise RuntimeError(f"Apify actor {actor} finished with status {run.status} and no results")
            log.warning("Apify actor %s finished with status %s; using %d partial results", actor, run.status, len(items))
        reported = float(run.usage_total_usd or 0)
        estimated = len(items) * self.s.float("apify_price_per_1000") / 1000
        self.costs.add_apify(len(items), max(reported, estimated))
        return items

    def reels_for(self, usernames: list[str], limit: int) -> dict[str, list[Reel]]:
        """Latest `limit` reels for each username, keyed by lowercase username."""
        out: dict[str, list[Reel]] = {u.lower(): [] for u in usernames}
        if not usernames:
            return out
        items = self._run(
            "reel_actor",
            {"usernames": usernames, "limit": limit},
            max_items=limit * len(usernames) + 10,
        )
        single = usernames[0].lower() if len(usernames) == 1 else ""
        for it in items:
            r = normalize_reel(it, default_owner=single)
            if r.is_video and r.owner in out:
                out[r.owner].append(r)
        return out

    def search_reels(self, keywords: list[str], limit: int) -> list[Reel]:
        items = self._run(
            "search_actor",
            {"keywords": keywords, "limit": limit},
            max_items=limit * len(keywords) + 10,
        )
        return [r for r in (normalize_reel(i) for i in items) if r.owner]

    def profiles(self, usernames: list[str]) -> list[Profile]:
        if not usernames:
            return []
        items = self._run("profile_actor", {"usernames": usernames}, max_items=len(usernames) + 5)
        return [p for p in (normalize_profile(i) for i in items) if p.username]

    def reels_by_url(self, urls: list[str]) -> list[Reel]:
        if not urls:
            return []
        items = self._run("post_actor", {"urls": urls, "limit": 1}, max_items=len(urls) + 5)
        return [normalize_reel(i) for i in items]
