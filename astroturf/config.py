"""Load and validate pipeline settings and subreddit targets."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    """Raised when a config file is missing, malformed, or invalid."""


@dataclass
class Settings:
    store_name: str = "merchmarket"
    lmstudio_base_url: str = "http://localhost:1234/v1"
    keyword_model: str = ""
    reply_model: str = ""
    max_replies_per_day: int = 5
    max_replies_per_sub_per_day: int = 2
    min_delay_seconds: int = 120
    max_delay_seconds: int = 600
    include_links: bool = False
    max_reply_words: int = 40
    max_comments_per_sub: int = 100


def load_settings(path) -> Settings:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"settings file not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"settings file is not valid JSON: {e}") from e

    lm = raw.get("lmstudio", {}) or {}
    limits = raw.get("limits", {}) or {}
    style = raw.get("style", {}) or {}

    s = Settings(
        store_name=str(raw.get("store_name", "merchmarket")),
        lmstudio_base_url=str(lm.get("base_url", "http://localhost:1234/v1")).rstrip("/"),
        keyword_model=str(lm.get("keyword_model", "")),
        reply_model=str(lm.get("reply_model", "")),
        max_replies_per_day=int(limits.get("max_replies_per_day", 5)),
        max_replies_per_sub_per_day=int(limits.get("max_replies_per_sub_per_day", 2)),
        min_delay_seconds=int(limits.get("min_delay_seconds", 120)),
        max_delay_seconds=int(limits.get("max_delay_seconds", 600)),
        include_links=bool(style.get("include_links", False)),
        max_reply_words=int(style.get("max_reply_words", 40)),
        max_comments_per_sub=int(raw.get("max_comments_per_sub", 100)),
    )

    if not s.store_name:
        raise ConfigError("store_name must be a non-empty string")
    if not s.keyword_model:
        raise ConfigError("lmstudio.keyword_model is required")
    if not s.reply_model:
        raise ConfigError("lmstudio.reply_model is required")
    for name in (
        "max_replies_per_day",
        "max_replies_per_sub_per_day",
        "min_delay_seconds",
        "max_delay_seconds",
        "max_reply_words",
        "max_comments_per_sub",
    ):
        if getattr(s, name) <= 0:
            raise ConfigError(f"{name} must be a positive integer")
    if s.min_delay_seconds > s.max_delay_seconds:
        raise ConfigError("min_delay_seconds must be <= max_delay_seconds")
    return s


@dataclass
class SubTarget:
    subreddit: str  # normalized "r/foo"
    enabled: bool = True
    max_replies_per_sub_per_day: int | None = None


def normalize_subreddit(name) -> str:
    n = str(name).strip().lower()
    if not n.startswith("r/"):
        n = "r/" + n
    return n


def load_subreddits(path) -> list[SubTarget]:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"subreddits file not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"subreddits file is not valid JSON: {e}") from e
    if isinstance(raw, dict):
        raw = raw.get("subreddits", [])
    if not isinstance(raw, list):
        raise ConfigError("subreddits.json must be a list of entries")

    out: list[SubTarget] = []
    for i, entry in enumerate(raw):
        if isinstance(entry, str):
            name, enabled, cap = entry, True, None
        elif isinstance(entry, dict) and "subreddit" in entry:
            name = entry["subreddit"]
            enabled = bool(entry.get("enabled", True))
            raw_cap = entry.get("max_replies_per_sub_per_day")
            cap = int(raw_cap) if raw_cap is not None else None
        else:
            raise ConfigError(
                f"subreddits.json entry {i} must be a string or an object with 'subreddit'"
            )
        out.append(SubTarget(subreddit=normalize_subreddit(name), enabled=enabled, max_replies_per_sub_per_day=cap))
    return out
