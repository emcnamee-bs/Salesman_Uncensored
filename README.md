# Salesman_Uncensored — merchmarket Astroturf Bot

Near-free Reddit marketing for **merchmarket**: a daily pipeline finds comments in target
subreddits that mention topics overlapping our catalog, generates one-sentence human-sounding
replies with local Qwen models (LM Studio), and posts them through the companion Chrome
extension "MerchMarket Astroturfer" from a dedicated astroturf profile.

## How it works (daily loop)

1. Your cron writes all categories + subcategories to `catalog/catalog.json` (pre-existing job — we just read it).
2. You scrape target subreddits with the **Web Scraper** Chrome extension on old.reddit.com and export JSON into `inbox/`.
3. One command does everything else:

   ```bash
   .venv/bin/python -m astroturf run            # real run (writes pending replies, updates state)
   .venv/bin/python -m astroturf run --dry-run  # preview only; state untouched
   .venv/bin/python -m astroturf run r/foo      # one-off target override
   ```

4. The pipeline: preflight (LM Studio up? models loaded?) → generate today's keyword list if missing (big Qwen) → parse `inbox/` → match keywords against comments → dedup + daily caps (before spending tokens) → generate replies (cheap Qwen, one sentence each) → write `out/replies-YYYY-MM-DD.json`.
5. Open the extension popup → load that file → **Preview** first week, then Post.

## Setup (once)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Edit `config/settings.json`: set `lmstudio.keyword_model` and `lmstudio.reply_model` to the exact model IDs loaded in LM Studio (`http://localhost:1234/v1`). Edit `config/subreddits.json` with your standing target list (per-sub caps supported).

Smoke test before touching Reddit:

```bash
.venv/bin/python -m astroturf check
```

Prints the reachable models, a sample keyword list, and one sample reply for quality judgment.

## Web Scraper rule setup (old.reddit.com)

Install the free **Web Scraper** extension. Create a rule named `astroturf-comments`:

- **Selector:** `div.thing.comment`
- **Fields:**

| Field name | Selector | Type | Notes |
|---|---|---|---|
| `permalink` | `.sublink` → attribute `href` | link | the comment's own permalink (timestamp link); relative URLs are fine — the parser resolves them and derives subreddit/post_id/comment_id from it |
| `body` | `div.md` | text | comment body |
| `author` | `a.author` | text | optional; blank is OK |
| `score` | `.score` → attribute `title` | number | optional; 0 if missing |

- **Scrape flow:** open `https://old.reddit.com/r/<sub>/hot/`, click into each of the top threads (start with ~10–20), and run Web Scraper's scrape on each thread page. Exports land as JSON files — drop them all into `inbox/` (any file name). The parser dedupes by comment id, so overlapping scrapes are safe.
- **Field aliases accepted:** the parser also understands `id`, `text`, `content`, `comment`, `user`, `username`, `points`, `link`, `url`, `post_id`, `title` — if your rule uses different names, either rename them in Web Scraper or extend the alias lists in `astroturf/inbox.py`.
- **Volume:** "top 100 hot comments" is a soft target; the pipeline processes up to `max_comments_per_sub` (default 100) normalized comments per sub from whatever you scraped.

## Extension install ("MerchMarket Astroturfer")

1. `chrome://extensions` → Developer mode → **Load unpacked** → select the `extension/` folder.
2. Log into Reddit in Chrome with your astroturf profile (dedicated browser profile recommended).
3. Popup: load today's `out/replies-YYYY-MM-DD.json`, choose Preview or Post, Start. The popup shows a live countdown between posts (delay range mirrors `config/settings.json` — keep them in sync; constants are at the top of `extension/popup.js`).
4. If Reddit changed its markup and posting fails with "reply link not found" / "reply textarea not found", update the `SELECTORS` block at the top of `extension/content.js` (see Task 11 checklist in the plan) and reload the extension.

## Go-live sequence (spec §10)

1. **Week 1 — dry runs:** `run --dry-run` daily on ONE low-stakes sub; read every preview reply in context before trusting it.
2. **Week 2 — Preview-only posts:** real run, but the extension stays in Preview mode; verify typing/pacing/submit behavior on throwaway comments.
3. **Go live:** flip to Post with conservative caps (`max_replies_per_day: 5`, `max_replies_per_sub_per_day: 2`, delays 2–10 min). Dial up as the account ages — every knob is in `config/settings.json`.

## Files & contracts

- `out/keywords-YYYY-MM-DD.json` — `{date, model, keywords[]}`; regenerated daily by the big Qwen; falls back to the last good list on failure.
- `out/replies-YYYY-MM-DD.json` — array of `{subreddit, post_id, comment_id, permalink, matched_keywords, comment_excerpt, reply, status}` where status is `pending` (real run) or `preview` (dry-run). Consumed by the extension.
- `data/state.json` — replied comment IDs + per-sub daily counters; makes re-runs safe and enforces caps before LLM calls.

## Tests

```bash
.venv/bin/python -m pytest tests/ -v
```

All unit tests run offline (stub HTTP server / fake LLM). `check` is the only live-LLM path.
