"""Normalize Web Scraper exports from inbox/ into CommentRecords.

Web Scraper field names vary by user rule, so we accept aliases and derive
subreddit/post_id/comment_id from the permalink whenever fields are missing.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

REDDIT_BASE = "https://old.reddit.com"


@dataclass
class CommentRecord:
    subreddit: str
    post_id: str
    post_title: str
    comment_id: str
    author: str
    score: int
    body: str
    permalink: str


def _first(d: dict, keys) -> object:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v
    return None


def _derive_from_permalink(permalink: str) -> tuple[str, str, str]:
    """Return (subreddit, post_id, comment_id) parsed from a reddit permalink."""
    m = re.search(r"/r/([^/]+)/comments/([a-z0-9]+)", permalink)
    sub = f"r/{m.group(1)}" if m else ""
    post_id = m.group(2) if m else ""
    comment_id = ""
    tail = re.search(r"/(?:t1_)?([a-z0-9]{4,})/?$", permalink.rstrip("/"))
    if tail:
        candidate = tail.group(1)
        if candidate != post_id and not candidate.isdigit():
            comment_id = candidate
    return sub, post_id, comment_id


def _to_record(d: dict) -> CommentRecord | None:
    body = _first(d, ("body", "text", "content", "comment"))
    permalink = str(_first(d, ("permalink", "link", "url")) or "")
    if not isinstance(body, str):
        return None

    sub, post_id, comment_id_from_link = _derive_from_permalink(permalink)
    comment_id = str(_first(d, ("comment_id", "id", "commentId", "_id")) or "")
    if not comment_id:
        comment_id = comment_id_from_link
    if not comment_id:
        return None

    author = str(_first(d, ("author", "user", "username")) or "")
    score_raw = _first(d, ("score", "points"))
    try:
        score = int(score_raw) if score_raw is not None else 0
    except (TypeError, ValueError):
        score = 0

    post_id = str(_first(d, ("post_id", "postId", "thread_id")) or post_id)
    subreddit = str(_first(d, ("subreddit",)) or sub)
    if subreddit and not subreddit.startswith("r/"):
        subreddit = "r/" + subreddit.lower()
    post_title = str(_first(d, ("post_title", "title")) or "")

    if permalink and not permalink.startswith("http"):
        permalink = urljoin(REDDIT_BASE + "/", permalink.lstrip("/"))

    return CommentRecord(
        subreddit=subreddit,
        post_id=post_id,
        post_title=post_title,
        comment_id=comment_id,
        author=author,
        score=score,
        body=body,
        permalink=permalink,
    )


def _extract_rows(data) -> list[dict]:
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in ("results", "data"):
            v = data.get(key)
            if isinstance(v, list):
                return [d for d in v if isinstance(d, dict)]
        # a single comment object
        if _first(data, ("body", "text", "content", "comment")):
            return [data]
    return []


def parse_inbox(inbox_dir) -> tuple[list[CommentRecord], list[str]]:
    inbox = Path(inbox_dir)
    records: list[CommentRecord] = []
    warnings: list[str] = []
    seen: set[str] = set()

    if not inbox.is_dir():
        return records, warnings

    for path in sorted(inbox.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            warnings.append(f"{path.name}: unreadable JSON ({e}); skipped")
            continue
        for row in _extract_rows(data):
            rec = _to_record(row)
            if rec is None:
                warnings.append(
                    f"{path.name}: comment missing body or id/permalink; skipped"
                )
                continue
            if rec.comment_id in seen:
                continue
            seen.add(rec.comment_id)
            records.append(rec)
    return records, warnings
