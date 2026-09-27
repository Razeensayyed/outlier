"""Running cost tally for a job, written to the Run Log tab."""

from __future__ import annotations

from dataclasses import dataclass, field

# USD per million tokens (input, output). Update if Anthropic changes prices.
CLAUDE_PRICES = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-5-5": (4.0, 20.0),
}
GROQ_PER_HOUR = {"whisper-large-v3": 0.111, "whisper-large-v3-turbo": 0.04}


@dataclass
class Costs:
    apify_items: int = 0
    apify_usd: float = 0.0
    claude_usd: float = 0.0
    groq_usd: float = 0.0
    tokens: dict[str, list[int]] = field(default_factory=dict)

    def add_apify(self, items: int, usd: float) -> None:
        self.apify_items += items
        self.apify_usd += usd

    def add_claude(self, model: str, usage) -> None:
        inp = (getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        cached = getattr(usage, "cache_read_input_tokens", 0) or 0
        out = getattr(usage, "output_tokens", 0) or 0
        pin, pout = CLAUDE_PRICES.get(model, (5.0, 25.0))
        self.claude_usd += (inp * pin + cached * pin * 0.1 + out * pout) / 1_000_000
        t = self.tokens.setdefault(model, [0, 0])
        t[0] += inp + cached
        t[1] += out

    def add_groq(self, model: str, seconds: float) -> None:
        hours = max(seconds, 10) / 3600  # Groq bills a 10s minimum per request
        self.groq_usd += hours * GROQ_PER_HOUR.get(model, 0.111)

    @property
    def total(self) -> float:
        return self.apify_usd + self.claude_usd + self.groq_usd

    def row(self) -> dict:
        return {
            "Apify items": self.apify_items,
            "Apify $": round(self.apify_usd, 4),
            "Claude $": round(self.claude_usd, 4),
            "Groq $": round(self.groq_usd, 4),
            "Total $": round(self.total, 4),
        }
