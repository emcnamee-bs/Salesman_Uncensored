"""Read the cron-written catalog.json and normalize it into CatalogItems.

The exact shape of catalog.json is owned by the user's cron job, so this
module walks arbitrary nesting and pulls out anything that looks like a
product entry (a dict with a name-ish key, or a bare string).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from astroturf.config import ConfigError


@dataclass
class CatalogItem:
    name: str
    category: str = ""
    subcategory: str = ""
    description: str = ""
    price: str = ""


_NAME_KEYS = ("name", "title", "product", "item")
_CATEGORY_KEYS = ("category", "cat", "theme")
_SUBCATEGORY_KEYS = ("subcategory", "sub_category", "subcat")
_DESC_KEYS = ("description", "desc", "details")
_PRICE_KEYS = ("price",)
_WRAPPER_KEYS = {"categories", "category", "subcategories", "subcategory", "items", "products", "data", "results"}


def _pick(d: dict, keys) -> str:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)):
            return str(v)
    return ""


def _walk(node, context=()) -> list[CatalogItem]:
    """Walk arbitrary nesting. `context` is the tuple of ancestor container
    names; context[0] becomes category and context[1] becomes subcategory.
    A dict with a name AND nested children is a container (its name extends
    the context); a named leaf dict or bare string is a product entry."""
    items: list[CatalogItem] = []
    if isinstance(node, dict):
        name = _pick(node, _NAME_KEYS)
        has_children = any(isinstance(v, (dict, list)) for v in node.values())
        cat = _pick(node, _CATEGORY_KEYS) or (context[0] if context else "")
        subcat = _pick(node, _SUBCATEGORY_KEYS) or (context[1] if len(context) > 1 else "")
        if name and not has_children:
            items.append(CatalogItem(
                name=name,
                category=cat,
                subcategory=subcat,
                description=_pick(node, _DESC_KEYS),
                price=_pick(node, _PRICE_KEYS),
            ))
        elif name and has_children:
            for v in node.values():
                if isinstance(v, (dict, list)):
                    items.extend(_walk(v, context + (name,)))
        else:
            # Unnamed dict: its keys may carry the hierarchy
            # ({"categories": {"Superheroes": {...}}}) — descend with key as context,
            # except generic wrapper keys which add no information.
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    ctx = context + () if str(k).lower() in _WRAPPER_KEYS else context + (str(k),)
                    items.extend(_walk(v, ctx))
    elif isinstance(node, list):
        for value in node:
            items.extend(_walk(value, context))
    elif isinstance(node, str) and node.strip():
        cat = context[0] if context else ""
        subcat = context[1] if len(context) > 1 else ""
        items.append(CatalogItem(name=node.strip(), category=cat, subcategory=subcat))
    return items


def load_catalog(path) -> list[CatalogItem]:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"catalog file not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"catalog file is not valid JSON: {e}") from e

    seen: set[str] = set()
    out: list[CatalogItem] = []
    for item in _walk(raw):
        key = item.name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def relevant_items(items: list, keywords: list[str]) -> list:
    """Rank catalog items by keyword overlap; cap 25; fallback first-10."""
    kws = [k.lower() for k in keywords if k]

    def score(item) -> int:
        hay = " ".join(
            [item.name, item.category, item.subcategory, item.description]
        ).lower()
        return sum(1 for k in kws if k and k in hay)

    scored = sorted(items, key=score, reverse=True)
    matched = [i for i in scored if score(i) > 0]
    rest = [i for i in scored if score(i) == 0]
    # matches first, then the remainder as context padding (cap 25);
    # when nothing matches at all, fall back to the first 10 items
    chosen = (matched + rest)[:25] if matched else items[:10]
    return chosen


def format_catalog_summary(items: list, limit: int = 100) -> str:
    lines = []
    for item in items[:limit]:
        parts = [item.name]
        if item.category:
            parts.append(item.category)
        if item.subcategory:
            parts.append(item.subcategory)
        lines.append(" - ".join(parts))
    return "\n".join(lines)
