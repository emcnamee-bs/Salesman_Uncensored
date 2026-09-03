"""Daily keyword-list generation via the bigger local Qwen model."""
from __future__ import annotations

import json
from datetime import date as _date
from pathlib import Path

from astroturf.catalog import format_catalog_summary


class KeywordGenerationError(Exception):
    """Raised when no usable keyword list can be produced or found."""


def extract_json_array(text: str) -> list[str]:
    """Pull the first balanced JSON array of strings out of LLM output.

    Tolerates prose and markdown fences around the array. Raises
    KeywordGenerationError when no valid non-empty string array is found.
    """
    start = text.find("[")
    while start != -1:
        depth = 0
        in_str = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            arr = json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break
                        out, seen = [], set()
                        for v in arr:
                            if isinstance(v, str):
                                s = " ".join(v.split())
                                key = s.lower()
                                if s and key not in seen:
                                    seen.add(key)
                                    out.append(s)
                        if out:
                            return out
                        break
        start = text.find("[", start + 1)
    raise KeywordGenerationError("no JSON array of strings found in model output")


def _load_dated_file(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    kws = data.get("keywords", [])
    return [k for k in kws if isinstance(k, str)]


def ensure_keywords(client, settings, items, out_dir, today=None) -> tuple[list[str], str]:
    """Return (keywords, source) where source is generated|cached|fallback.

    - Today's file exists  -> ("...", "cached")
    - Generation succeeds  -> save dated file, ("...", "generated")
    - Generation fails/empty and an older good list exists -> ("...", "fallback")
    - Generation fails/empty and no prior list -> KeywordGenerationError
    """
    today = today or _date.today()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today_file = out_dir / f"keywords-{today.isoformat()}.json"

    if today_file.exists():
        return _load_dated_file(today_file), "cached"

    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "keyword_generation.md"
    template = prompt_path.read_text(encoding="utf-8")
    user_prompt = template.replace("{store_name}", settings.store_name).replace(
        "{catalog_summary}", format_catalog_summary(items)
    )

    keywords: list[str] = []
    try:
        raw = client.chat("You output strict JSON.", user_prompt, model=settings.keyword_model, max_tokens=1500)
        keywords = extract_json_array(raw)
    except Exception as e:  # LLMError or parse failure
        if not isinstance(e, KeywordGenerationError):
            raise KeywordGenerationError(f"keyword generation failed: {e}") from e

    if keywords:
        today_file.write_text(
            json.dumps({"date": today.isoformat(), "model": settings.keyword_model, "keywords": keywords}, indent=2),
            encoding="utf-8",
        )
        return keywords, "generated"

    prior = sorted(out_dir.glob("keywords-*.json"))
    if prior:
        return _load_dated_file(prior[-1]), "fallback"
    raise KeywordGenerationError(
        f"keyword generation failed and no previous list exists in {out_dir}"
    )
