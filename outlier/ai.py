"""All Claude calls. Every call returns a validated Pydantic object (structured outputs)."""

from __future__ import annotations

from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from .costs import Costs
from .media import Frame

# Fixed taxonomies keep the Sunday tallies meaningful: the AI must pick from these lists.
HookStyle = Literal[
    "Bold claim", "Question", "Shocking number/stat", "Contrarian / myth-bust", "Mistake / warning",
    "Result first / proof", "Story opener", "How-to promise", "List / countdown", "Curiosity gap",
    "Relatable pain point", "Demo / show-don't-tell", "News / trend", "Other",
]
StoryStructure = Literal[
    "Problem -> Solution", "Listicle", "Tutorial / step-by-step", "Before -> After",
    "Personal story", "Myth vs fact", "Comparison / versus", "Reaction / commentary",
    "Demo / walkthrough", "Case study / example", "Other",
]
VisualFormat = Literal[
    "Talking head", "Green screen", "Screen recording", "Voiceover + B-roll", "Text on screen only",
    "Skit / acting", "Podcast / interview clip", "Split screen / reaction", "Slideshow",
    "Vlog / day in the life", "Other",
]
AudioType = Literal[
    "Original voice only", "Voice + background music", "Trending sound", "Music only",
    "AI / TTS voiceover", "Other",
]
Brick = Literal["Topic", "Angle", "Hook", "Story structure", "Visual format", "Key visuals", "Audio"]


class Relevance(BaseModel):
    score: int = Field(description="0-10, how well this fits the niche and its audience")
    reason: str = Field(description="One short sentence")


class Bricks(BaseModel):
    topic: str = Field(description="What the reel is about, one line")
    topic_theme: str = Field(description="2-4 word reusable theme label, e.g. 'ChatGPT prompts', 'WhatsApp automation'")
    angle: str = Field(description="The specific take / perspective on the topic")
    hook_spoken: str = Field(description="First spoken line(s), verbatim if possible; '' if none")
    hook_text: str = Field(description="On-screen text in the first 3 seconds; '' if none")
    hook_visual: str = Field(description="What the viewer sees in the first 3 seconds")
    hook_style: HookStyle
    story_structure: StoryStructure
    structure_notes: str = Field(description="Beat-by-beat outline, e.g. 'Hook -> 3 tools -> CTA'")
    visual_format: VisualFormat
    key_visuals: str = Field(description="Notable visuals, props, edits, captions style, b-roll")
    audio_type: AudioType
    audio_notes: str = Field(description="Sound name / music mood / voice style")
    gap: str = Field(description="What they did weakly that a creator in this niche could do better")


class ThemeAssignment(BaseModel):
    index: int
    theme: str


class Themes(BaseModel):
    assignments: list[ThemeAssignment]


class BrickPlan(BaseModel):
    brick: Brick
    decision: Literal["Hold", "Remix"]
    original: str = Field(description="What the source reel did for this brick")
    plan: str = Field(description="What our version does (same as original if Hold)")


class Remix(BaseModel):
    bricks: list[BrickPlan] = Field(description="Exactly one entry per brick, all 7 bricks")
    hook_options: list[str] = Field(description="3 alternative opening lines in the creator's language")
    script_outline: str = Field(description="Short beat-by-beat script outline for our version")


class AI:
    def __init__(self, api_key: str, analysis_model: str, fast_model: str, costs: Costs, niche: str, language: str):
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=4)
        self.analysis_model = analysis_model
        self.fast_model = fast_model
        self.costs = costs
        self.system = (
            "You help a short-form video creator research content ideas.\n"
            f"Creator's niche: {niche}\n"
            f"Reels are mostly in: {language}. Transcripts may be Hinglish (Hindi written in Roman script); "
            "understand them natively. Write your answers in English, but quote hooks in their original language."
        )

    def _parse(self, model: str, content, schema, *, thinking: bool, max_tokens: int = 16000):
        kwargs = {}
        if thinking:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": "medium"}
        resp = self.client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=self.system,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
            **kwargs,
        )
        self.costs.add_claude(model, resp.usage)
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"Claude declined: {getattr(resp.stop_details, 'explanation', '')}")
        if resp.parsed_output is None:
            raise RuntimeError(f"Claude returned no parsable output (stop_reason={resp.stop_reason})")
        return resp.parsed_output

    # ---- Phase 5: relevance -----------------------------------------------------------
    def reel_relevance(self, handle: str, caption: str, transcript: str) -> Relevance:
        text = (
            "Does this reel's topic fit my niche and speak to my audience? Score 0-10 "
            "(10 = squarely on-niche idea I could remake; 5 = adjacent; 0 = unrelated).\n\n"
            f"Creator: @{handle}\nCaption:\n{caption[:2000]}\n\nTranscript:\n{transcript[:6000] or '(none)'}"
        )
        return self._parse(self.fast_model, text, Relevance, thinking=False, max_tokens=1024)

    # ---- Phase 2: account relevance -------------------------------------------------------
    def account_relevance(self, handle: str, bio: str, captions: list[str]) -> Relevance:
        caps = "\n---\n".join(c[:400] for c in captions[:8])
        text = (
            "Is this Instagram creator worth adding to my watch list? They should talk to my niche's "
            "audience (adjacent niches like entrepreneurship/productivity/marketing can score 5-7). Score 0-10.\n\n"
            f"@{handle}\nBio: {bio[:500]}\n\nRecent captions:\n{caps}"
        )
        return self._parse(self.fast_model, text, Relevance, thinking=False, max_tokens=1024)

    # ---- Phase 6: 7-brick breakdown ---------------------------------------------------------
    def bricks(self, *, handle: str, views: int, score: float, caption: str, audio: str,
               transcript: str, frames: list[Frame]) -> Bricks:
        content: list[dict] = []
        for f in frames:
            content.append({"type": "text", "text": f"Frame at {f.t:.1f}s:"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": f.jpeg_b64}})
        content.append({
            "type": "text",
            "text": (
                f"This reel by @{handle} got {views:,} views, {score}x the creator's median, so the idea "
                "clearly worked. Break it into the 7 bricks (Topic, Angle, Hook [spoken/text/visual], Story "
                "structure, Visual format, Key visuals, Audio) and name the Gap - what it did weakly that I "
                "could do better. The frames above are in time order; the first six cover the first 3 seconds "
                f"(the hook).\n\nCaption:\n{caption[:2000]}\n\nAudio track: {audio or 'unknown'}\n\n"
                f"Transcript:\n{transcript[:12000] or '(no speech detected)'}"
            ),
        })
        return self._parse(self.analysis_model, content, Bricks, thinking=True)

    # ---- Phase 7: group topics into themes ------------------------------------------------------
    def group_topics(self, topics: list[str]) -> dict[int, str]:
        listing = "\n".join(f"{i}. {t}" for i, t in enumerate(topics))
        text = (
            "Group these reel topics into a small set of recurring themes (2-4 words each). Reuse the same "
            "theme label for topics that are really the same idea so I can count repeats. Return one "
            f"assignment per index.\n\n{listing}"
        )
        res = self._parse(self.analysis_model, text, Themes, thinking=False, max_tokens=4000)
        return {a.index: a.theme for a in res.assignments}

    # ---- Phase 8: Hold / Remix ------------------------------------------------------------------
    def remix(self, *, outlier: dict, whats_working: str) -> Remix:
        brick_text = "\n".join(
            f"- {k}: {outlier.get(k, '')}"
            for k in ["Topic", "Angle", "Hook (spoken)", "Hook (text)", "Hook (visual)", "Hook style",
                      "Story structure", "Visual format", "Key visuals", "Audio", "Audio type", "Gap"]
        )
        text = (
            "I want to make my own version of this outlier reel. For each of the 7 bricks decide Hold (keep "
            "the proven part - usually topic, audio mood, some visuals) or Remix (change it - usually angle, "
            "hook, format), using what's currently working in my niche and fixing the Gap. Then give 3 hook "
            "options and a short script outline.\n\n"
            f"Source reel ({outlier.get('Link', '')}, {outlier.get('Outlier score', '')}x):\n{brick_text}\n\n"
            f"What's working now in my niche:\n{whats_working or '(no weekly review yet)'}"
        )
        return self._parse(self.analysis_model, text, Remix, thinking=True)
