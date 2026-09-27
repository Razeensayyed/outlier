"""Speech-to-text with Groq's hosted Whisper (cheap and handles Hinglish well)."""

from __future__ import annotations

from pathlib import Path

from groq import Groq

from .costs import Costs

PROMPT = (
    "Instagram reel. Speaker may mix Hindi and English (Hinglish). "
    "Write Hindi words in Roman script, e.g. 'aaj main aapko batata hoon ChatGPT ka ek hack'."
)


class Transcriber:
    def __init__(self, api_key: str, model: str, costs: Costs):
        self.client = Groq(api_key=api_key)
        self.model = model
        self.costs = costs

    def transcribe(self, audio: Path, seconds: float) -> str:
        with open(audio, "rb") as f:
            res = self.client.audio.transcriptions.create(
                file=(audio.name, f.read()),
                model=self.model,
                prompt=PROMPT,
                response_format="text",
                temperature=0.0,
            )
        self.costs.add_groq(self.model, seconds)
        text = res if isinstance(res, str) else getattr(res, "text", "")
        return text.strip()
