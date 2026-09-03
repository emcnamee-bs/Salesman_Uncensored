"""Command-line entry point: python -m astroturf run|check."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as _date
from pathlib import Path

from astroturf.catalog import load_catalog
from astroturf.config import ConfigError, Settings, SubTarget, load_settings, load_subreddits, normalize_subreddit
from astroturf.inbox import parse_inbox
from astroturf.keywords import KeywordGenerationError, ensure_keywords
from astroturf.llm import LMStudioClient, LLMError
from astroturf.matcher import match_comments
from astroturf.replies import generate_replies
from astroturf.state import State, load_state, save_state


def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def run_pipeline(settings: Settings, targets: list[SubTarget], client, base_dir: Path, today=None, dry_run=False) -> dict:
    today = (today or _date.today()).isoformat()
    base_dir = Path(base_dir)

    # 1. preflight — fail fast before spending tokens
    available = set(client.models())
    for name in ("keyword_model", "reply_model"):
        model = getattr(settings, name)
        if model not in available:
            raise RuntimeError(
                f"preflight failed: model '{model}' ({name}) not loaded in LM Studio. "
                f"Available models: {sorted(available)}"
            )

    # 2. catalog + keywords (dedup/fallback handled inside ensure_keywords)
    items = load_catalog(base_dir / "catalog" / "catalog.json")
    if not items:
        raise RuntimeError("catalog is empty — check catalog/catalog.json (written by your cron)")
    keywords, kw_source = ensure_keywords(client, settings, items, base_dir / "out", today=_date.fromisoformat(today))

    # 3. parse inbox
    records, warnings = parse_inbox(base_dir / "inbox")

    # 4. filter to enabled targets + per-sub comment cap (file order preserved)
    enabled = {t.subreddit: t for t in targets if t.enabled}
    per_sub_seen: dict[str, int] = {}
    target_records = []
    for rec in records:
        if rec.subreddit not in enabled:
            continue
        n = per_sub_seen.get(rec.subreddit, 0)
        if n >= settings.max_comments_per_sub:
            continue
        per_sub_seen[rec.subreddit] = n + 1
        target_records.append(rec)

    # 5. match keywords
    flagged = match_comments(target_records, keywords)

    # 6. state dedup + caps BEFORE any LLM call
    state = load_state(base_dir / "data" / "state.json")
    to_generate = []
    skipped_replied = 0
    skipped_cap = 0
    batch_sub_counts: dict[str, int] = {}
    for fc in flagged:
        sub = fc.comment.subreddit
        if state.already_replied(fc.comment.comment_id):
            skipped_replied += 1
            continue
        target = enabled[sub]
        cap = (target.max_replies_per_sub_per_day or settings.max_replies_per_sub_per_day)
        used_sub = state.sub_count(today, sub) + batch_sub_counts.get(sub, 0)
        global_used = state.global_count(today) + len(to_generate)
        if used_sub >= cap or global_used >= settings.max_replies_per_day:
            skipped_cap += 1
            continue
        batch_sub_counts[sub] = batch_sub_counts.get(sub, 0) + 1
        to_generate.append(fc)

    # 7. generate replies (cheap model)
    entries, skips = generate_replies(client, settings, to_generate, items, dry_run=dry_run)

    # 8. write replies file
    out_dir = base_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    replies_file = out_dir / f"replies-{today}.json"
    replies_file.write_text(json.dumps([e.to_dict() for e in entries], indent=2), encoding="utf-8")

    # 9. mark state (dry-run leaves state untouched so a real run can follow)
    if not dry_run:
        for e in entries:
            state.mark_replied(e.comment_id, e.subreddit, today)
        save_state(state, base_dir / "data" / "state.json")

    summary = {
        "date": today,
        "dry_run": dry_run,
        "keywords_source": kw_source,
        "keyword_count": len(keywords),
        "comments_parsed": len(records),
        "warnings": warnings,
        "flagged": len(flagged),
        "skipped_replied": skipped_replied,
        "skipped_cap": skipped_cap,
        "generated": len(entries),
        "skips": skips,
        "replies_file": str(replies_file),
    }
    return summary


def _print_summary(summary: dict) -> None:
    print(f"=== astroturf run {summary['date']}{' (dry-run)' if summary['dry_run'] else ''} ===")
    print(f"keywords: {summary['keyword_count']} ({summary['keywords_source']})")
    print(f"inbox comments parsed: {summary['comments_parsed']}")
    for w in summary["warnings"]:
        print(f"  warning: {w}")
    print(f"flagged by keywords: {summary['flagged']}")
    print(f"skipped (already replied): {summary['skipped_replied']}")
    print(f"skipped (daily cap): {summary['skipped_cap']}")
    for s in summary["skips"]:
        print(f"  skip: {s}")
    print(f"replies generated: {summary['generated']} -> {summary['replies_file']}")


def cmd_check(settings: Settings, client, base_dir: Path) -> int:
    """Live smoke test: hit LM Studio, print a sample keyword list and one reply."""
    try:
        models = client.models()
    except LLMError as e:
        print(f"FAIL: cannot reach LM Studio — {e}")
        return 1
    print(f"LM Studio reachable. Models loaded: {models}")

    for name in ("keyword_model", "reply_model"):
        model = getattr(settings, name)
        if model not in models:
            print(f"FAIL: '{model}' ({name}) is not loaded")
            return 1

    items = load_catalog(base_dir / "catalog" / "catalog.json")
    if not items:
        print("FAIL: catalog empty — check catalog/catalog.json")
        return 1

    keywords, source = ensure_keywords(client, settings, items, base_dir / "out")
    print(f"\nKeyword list ({source}, {len(keywords)} entries) — first 10:")
    for k in keywords[:10]:
        print(f"  - {k}")

    from astroturf.inbox import CommentRecord
    from astroturf.matcher import FlaggedComment

    sample = FlaggedComment(
        comment=CommentRecord(
            subreddit="r/sample", post_id="p1", post_title="Sample thread about the black suit",
            comment_id="s1", author="someone", score=10,
            body="the way the black suit moves with him in that scene is actually insane",
            permalink="",
        ),
        matched_keywords=["black suit"],
    )
    entries, skips = generate_replies(client, settings, [sample], items)
    if entries:
        print("\nSample reply (quality check before touching Reddit):")
        print(f"  {entries[0].reply}")
    else:
        print(f"\nFAIL: sample reply not generated — {skips}")
        return 1
    print("\ncheck OK")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="astroturf", description="merchmarket Reddit astroturf pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run the daily pipeline")
    run_p.add_argument("--dry-run", action="store_true", help="write replies with status 'preview', do not touch state")
    run_p.add_argument("subreddits", nargs="*", help="override target list, e.g. r/foo r/bar")

    sub.add_parser("check", help="live smoke test against LM Studio (prints sample keywords + reply)")

    args = parser.parse_args(argv)
    base_dir = _base_dir()

    try:
        settings = load_settings(base_dir / "config" / "settings.json")
        if args.command == "run" and args.subreddits:
            targets = [SubTarget(subreddit=normalize_subreddit(s), enabled=True) for s in args.subreddits]
        else:
            targets = load_subreddits(base_dir / "config" / "subreddits.json")
    except ConfigError as e:
        print(f"config error: {e}")
        return 1

    client = LMStudioClient(base_url=settings.lmstudio_base_url)

    if args.command == "check":
        return cmd_check(settings, client, base_dir)

    try:
        summary = run_pipeline(settings, targets, client, base_dir, dry_run=args.dry_run)
    except (RuntimeError, ConfigError, KeywordGenerationError, LLMError) as e:
        print(f"run failed: {e}")
        return 1
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
