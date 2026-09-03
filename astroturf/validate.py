"""Code-enforced reply style rules (spec section 7)."""
from __future__ import annotations

import re

from astroturf.config import Settings


def validate_reply(text: str, settings: Settings) -> tuple[bool, str]:
    t = text.strip()
    if not t:
        return False, "reply is empty"

    # links first: real URLs contain multiple dots and would otherwise be
    # misreported as a two-sentence violation
    if not settings.include_links and re.search(r"(https?://|www\.)", t):
        return False, "reply contains a link but include_links is false"

    sentences = len(re.findall(r"[.!?]+", t))
    if sentences >= 2:
        return False, f"expected one sentence, found {sentences} terminal punctuation runs"

    words = len(t.split())
    if words > settings.max_reply_words:
        return False, f"{words} words exceeds max of {settings.max_reply_words}"

    store = settings.store_name.lower()
    if store:
        count = t.lower().count(store)
        if count > 1:
            return False, f"store name appears {count} times (max 1)"

    return True, ""
