"""Dedup + daily counters persisted to data/state.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class State:
    replied: dict = field(default_factory=dict)        # comment_id -> {"date", "subreddit"}
    daily_counts: dict = field(default_factory=dict)   # date -> {"global": int, "subs": {sub: int}}

    def already_replied(self, comment_id: str) -> bool:
        return comment_id in self.replied

    def _day(self, date: str) -> dict:
        day = self.daily_counts.get(date)
        if not isinstance(day, dict):
            day = {"global": 0, "subs": {}}
            self.daily_counts[date] = day
        return day

    def global_count(self, date: str) -> int:
        return int(self._day(date).get("global", 0))

    def sub_count(self, date: str, subreddit: str) -> int:
        subs = self._day(date).setdefault("subs", {})
        return int(subs.get(subreddit, 0))

    def mark_replied(self, comment_id: str, subreddit: str, date: str) -> None:
        if comment_id in self.replied:
            return
        self.replied[comment_id] = {"date": date, "subreddit": subreddit}
        day = self._day(date)
        day["global"] = int(day.get("global", 0)) + 1
        subs = day.setdefault("subs", {})
        subs[subreddit] = int(subs.get(subreddit, 0)) + 1


def load_state(path) -> State:
    p = Path(path)
    if not p.exists():
        return State()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return State()
    replied = raw.get("replied", {})
    daily_counts = raw.get("daily_counts", {})
    if not isinstance(replied, dict) or not isinstance(daily_counts, dict):
        return State()
    return State(replied=replied, daily_counts=daily_counts)


def save_state(state: State, path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"replied": state.replied, "daily_counts": state.daily_counts}
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
