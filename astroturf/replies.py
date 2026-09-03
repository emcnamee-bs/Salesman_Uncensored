"""Dispatch flagged comments to the cheap local Qwen and collect replies."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from astroturf.catalog import format_catalog_summary, relevant_items
from astroturf.config import Settings
from astroturf.matcher import FlaggedComment
from astroturf.validate import validate_reply


@dataclass
class ReplyEntry:
    subreddit: str
    post_id: str
    comment_id: str
    permalink: str
    matched_keywords: list = field(default_factory=list)
    comment_excerpt: str = ""
    reply: str = ""
    status: str = "pending"  # "pending" | "preview"

    def to_dict(self) -> dict:
        return {
            "subreddit": self.subreddit,
            "post_id": self.post_id,
            "comment_id": self.comment_id,
            "permalink": self.permalink,
            "matched_keywords": list(self.matched_keywords),
            "comment_excerpt": self.comment_excerpt,
            "reply": self.reply,
            "status": self.status,
        }


def _excerpt(body: str, limit: int = 200) -> str:
    b = " ".join(body.split())
    if len(b) <= limit:
        return b
    return b[: limit - 3].rstrip() + "..."


def _build_prompt(template: str, settings: Settings, fc: FlaggedComment, catalog_items: list) -> str:
    relevant = relevant_items(catalog_items, fc.matched_keywords)
    return (
        template.replace("{store_name}", settings.store_name)
        .replace("{post_title}", fc.comment.post_title or "(unknown)")
        .replace("{comment_excerpt}", _excerpt(fc.comment.body))
        .replace("{matched_keywords}", ", ".join(fc.matched_keywords))
        .replace("{catalog_context}", format_catalog_summary(relevant, limit=25) or "(no matching items)")
    )


def generate_replies(client, settings: Settings, flagged: list[FlaggedComment], catalog_items: list, dry_run: bool = False):
    """Return (entries, skip_log). One LLM call per comment; on style
    violation regenerate once at higher temperature, then log + skip."""
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "astroturf_reply.md"
    template = prompt_path.read_text(encoding="utf-8")

    entries: list[ReplyEntry] = []
    skips: list[str] = []
    status = "preview" if dry_run else "pending"

    for fc in flagged:
        c = fc.comment
        user_prompt = _build_prompt(template, settings, fc, catalog_items)
        reply = None
        try:
            candidate = client.chat(
                "You write one casual Reddit sentence. Return only the sentence.",
                user_prompt,
                model=settings.reply_model,
                temperature=0.8,
                max_tokens=120,
            )
            ok, reason = validate_reply(candidate, settings)
            if not ok:
                candidate = client.chat(
                    "You write one casual Reddit sentence. Return only the sentence.",
                    user_prompt,
                    model=settings.reply_model,
                    temperature=1.0,
                    max_tokens=120,
                )
                ok, reason = validate_reply(candidate, settings)
            if not ok:
                skips.append(f"{c.subreddit} t1_{c.comment_id}: style violation after retry ({reason})")
                continue
            reply = candidate.strip()
        except Exception as e:  # LLMError or anything else from the model call
            skips.append(f"{c.subreddit} t1_{c.comment_id}: generation failed ({e})")
            continue

        entries.append(
            ReplyEntry(
                subreddit=c.subreddit,
                post_id=c.post_id,
                comment_id=c.comment_id,
                permalink=c.permalink,
                matched_keywords=list(fc.matched_keywords),
                comment_excerpt=_excerpt(c.body),
                reply=reply,
                status=status,
            )
        )
    return entries, skips
