"""Download a reel and cut it into audio + frames with ffmpeg."""

from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclass
class Frame:
    t: float  # seconds into the video
    jpeg_b64: str


def download(url: str, dest: Path) -> Path:
    with requests.get(url, headers={"User-Agent": UA}, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    if dest.stat().st_size < 10_000:
        raise RuntimeError("downloaded file is too small to be a video (link probably expired)")
    return dest


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def duration(video: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


def extract_audio(video: Path, dest: Path) -> Path | None:
    try:
        _ffmpeg("-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", str(dest))
    except subprocess.CalledProcessError:
        return None  # video without an audio track
    return dest if dest.exists() and dest.stat().st_size > 1000 else None


def extract_frames(video: Path, workdir: Path, max_frames: int = 16) -> list[Frame]:
    """Dense frames for the hook (first 3s at 2fps), then one every 3s for the rest."""
    length = duration(video)
    times = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    t = 3.0
    while t < length - 0.3:
        times.append(t)
        t += 3.0
    times = [x for x in times if x < length]
    if len(times) > max_frames:
        hook, rest = times[:6], times[6:]
        keep = max_frames - len(hook)
        step = len(rest) / keep if keep > 0 else len(rest) + 1
        times = hook + [rest[int(i * step)] for i in range(max(keep, 0))]

    frames = []
    for i, ts in enumerate(times):
        out = workdir / f"frame_{i:02d}.jpg"
        _ffmpeg("-ss", f"{ts:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "5", str(out))
        if out.exists():
            frames.append(Frame(ts, base64.standard_b64encode(out.read_bytes()).decode()))
    return frames
