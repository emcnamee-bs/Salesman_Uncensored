"""Match inbox comments against the day's keyword list."""
from __future__ import annotations

import re
from dataclasses import dataclass

from astroturf.inbox import CommentRecord


@dataclass
class FlaggedComment:
    comment: CommentRecord
    matched_keywords: list[str]


def _keyword_pattern(keyword: str) -> re.Pattern:
    k = keyword.strip()
    if " " in k:  # phrase: plain substring, case-insensitive
        return re.compile(re.escape(k), flags=re.IGNORECASE)
    # single word/token: require a non-alphanumeric boundary so "venom"
    # does not match inside "symbiotevenom"; also safe for specials like c++
    return re.compile(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", flags=re.IGNORECASE)


def match_comments(records: list[CommentRecord], keywords: list[str]) -> list[FlaggedComment]:
    compiled = [(k, _keyword_pattern(k)) for k in keywords if k and k.strip()]
    flagged: list[FlaggedComment] = []
    for rec in records:
        hits = [k for k, pat in compiled if pat.search(rec.body)]
        if hits:
            flagged.append(FlaggedComment(comment=rec, matched_keywords=hits))
    return flagged
