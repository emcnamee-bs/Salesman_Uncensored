# Astroturf Bot — Design Spec

- **Date:** 2026-09-02
- **Status:** Approved (brainstorming complete, pending implementation plan)
- **Repo:** `emcnamee-bs/Salesman_Uncensored` (local: `/Users/eamonmcnamee/Downloads/Salesman_Uncensored`)
- **Runtime host:** local MacBook (macOS), Python 3 + Chrome

## 1. Goal & Background

Create near-free marketing for **merchmarket**, an online merchandise store with rotating themes (e.g., superheroes). The system finds Reddit comments in target subreddits that mention topics overlapping our catalog, then posts a subtle, human-sounding reply from a dedicated astroturf profile — as if a real customer who owns the product is weighing in on the thread.

**Core loop (daily):**
1. A local Qwen instance generates a comprehensive keyword list for the current catalog.
2. The top 100 "hot" comments of each target subreddit are scraped via the **Web Scraper** Chrome extension on old.reddit.com and exported to JSON.
3. Comments matching any keyphrase are flagged (with the matched keyphrase = the "conjoining factor").
4. Each flagged comment is dispatched to a cheap local Qwen with a harness prompt that makes it act like a real merchmarket customer: acknowledge what the commenter said, then subtly reference our product tied to the conjoining factor.
5. A companion Chrome extension ("MerchMarket Astroturfer") places each generated reply into the actual comment's reply box and posts it with human-like pacing.

**Non-goals (v1):**
- No Reddit API/OAuth (browser-first by design).
- No automated scraping (Web Scraper is the manual step; Playwright is a future upgrade path).
- No links in replies (name-drops only).
- No multi-platform support beyond Reddit.

## 2. Chosen Approach

**File-based pipeline with a thin extension.** One Python command does all LLM work and writes a replies file; the extension's only job is stealth delivery (find comment → type → submit). Every stage is an inspectable file on disk; prompts live in `prompts/*.md` for easy iteration; the extension stays small and dumb.

Rejected alternatives: smart-extension/thin-Python (prompt iteration in browser JS, harder debugging) and full Playwright automation (heavier machinery, less "manual human" story). Both remain future options.

## 3. Repository Layout

```
Salesman_Uncensored/
├── astroturf/               # Python package (the pipeline)
│   ├── cli.py               # `python -m astroturf run [--dry-run] [r/sub ...]`
│   ├── config.py            # loads + validates settings & subreddit targets
│   ├── catalog.py           # reads cron-written catalog.json → product context
│   ├── keywords.py          # daily keyword-list generation (LM Studio, big Qwen)
│   ├── matcher.py           # matches inbox comments against the day's keywords
│   ├── replies.py           # dispatches flagged comments to cheap Qwen → reply text
│   ├── llm.py               # thin OpenAI-compatible client for LM Studio
│   └── state.py             # dedup + daily counters (data/state.json)
├── extension/               # "MerchMarket Astroturfer" — MV3, vanilla JS, no build step
│   ├── manifest.json
│   ├── popup.js / popup.html  # load replies file, review queue, Start/Pause
│   └── content.js           # find comment by ID → click Reply → type w/ pacing → submit
├── prompts/
│   ├── keyword_generation.md  # iterate prompts without touching code
│   └── astroturf_reply.md     # the "be a real customer" harness prompt
├── config/
│   ├── settings.json        # LM Studio URL, model names, caps, delay ranges, store name
│   └── subreddits.json      # standing target list + per-sub overrides
├── catalog/catalog.json     # ← user's cron writes this (categories + subcategories)
├── inbox/                   # ← Web Scraper exports land here (gitignored contents)
├── out/                     # keywords-DATE.json, replies-DATE.json (gitignored)
├── data/state.json          # dedup + counters (gitignored)
└── tests/
```

## 4. Components

1. **Keyword generator** — once per day: reads `catalog/catalog.json`, asks the bigger Qwen for a comprehensive keyphrase list covering theme terms, product names, character/hero names, fandom nicknames, and related phrases. Saved to `out/keywords-DATE.json`; skipped if today's file already exists.
2. **Inbox parser** — normalizes Web Scraper exports into one common comment record: `{subreddit, post_id, post_title, comment_id, author, score, body, permalink}`. The README documents exactly how to build the Web Scraper rule for old-reddit hot pages so exports contain these fields.
3. **Matcher** — case-insensitive phrase/word-boundary matching of keywords against comment bodies; records which keyphrase(s) triggered each flag (the conjoining factor handed to the agent).
4. **Reply generator** — for each flagged comment (respecting per-sub + global daily caps), calls the cheap Qwen with: harness prompt + post title + flagged comment + matched keyphrase + a slice of relevant catalog items → one concise, human-sounding reply.
5. **State** — `data/state.json`: replied-to comment IDs, per-sub daily counts, last keyword date. Prevents double-replies across runs and enforces caps before spending tokens.
6. **Extension (MerchMarket Astroturfer)** — MV3, vanilla JS: loads `replies-DATE.json`, shows the queue with thread links, then for each entry navigates to the permalink, finds the comment element by its Reddit ID (`t1_<id>`), clicks Reply, types with randomized human pacing, submits, waits for confirmation, logs the result. Includes **Preview mode** (fills box without submitting).

## 5. Daily Data Flow

```
user's cron ──► catalog/catalog.json          (pre-existing, not our code)
user        ──► inbox/*.json                   (Web Scraper exports, one file per sub/page)
              │
python -m astroturf run                        (one command does the rest)
              ├─ 1. preflight: LM Studio up? model loaded? (GET /v1/models)
              ├─ 2. keywords: generate today's list if missing (big Qwen)
              ├─ 3. parse inbox → normalized comment records
              ├─ 4. match vs keywords → flagged set (+ which keyphrase hit)
              ├─ 5. state check: drop already-replied IDs, apply daily caps
              └─ 6. generate replies (cheap Qwen) → out/replies-DATE.json
user        ──► extension: load file → review queue → Preview or Post
```

**Flow rules:**
- **Dedup before tokens** — state check happens before any LLM call; a comment flagged on consecutive days costs nothing the second time.
- **Caps enforced pre-generation** — over-cap flags are logged as `skipped_cap` in the run summary, not silently dropped or over-posted.
- **Keyword fallback** — if today's generation fails or is empty, reuse the most recent good list with a warning instead of halting the day.
- **Inbox is append-only per run** — processed files remain in `inbox/` (tracked via state); re-runs are safe; nothing deleted without config saying so.
- **Comment volume** — Web Scraper captures whatever the page renders, so "top 100 hot comments" is a soft target: the pipeline processes all normalized comments for a sub from the inbox, capped at `max_comments_per_sub` (default 100, configurable). To reach the cap, scrape the hot listing plus individual thread pages; exports are deduped by `comment_id`.

## 6. File Contracts

### `config/settings.json`
```json
{
  "store_name": "merchmarket",
  "lmstudio": {
    "base_url": "http://localhost:1234/v1",
    "keyword_model": "qwen2.5-14b-instruct",
    "reply_model": "qwen2.5-7b-instruct"
  },
  "limits": {
    "max_replies_per_day": 5,
    "max_replies_per_sub_per_day": 2,
    "min_delay_seconds": 120,
    "max_delay_seconds": 600
  },
  "style": {
    "include_links": false,
    "max_reply_words": 40
  }
}
```

### `config/subreddits.json`
```json
[
  { "subreddit": "r/spiderman", "enabled": true },
  { "subreddit": "r/venom", "enabled": true, "max_replies_per_sub_per_day": 1 }
]
```

### `out/replies-DATE.json` (consumed by the extension)
```json
[
  {
    "subreddit": "r/spiderman",
    "post_id": "1abc",
    "comment_id": "1xyz",
    "permalink": "https://old.reddit.com/r/spiderman/comments/1abc/_/1xyz/",
    "matched_keywords": ["symbiote black suit"],
    "comment_excerpt": "...love how the black suit actually moves with him...",
    "reply": "the way it clings to him in that scene is wild, honestly picked up a black-suit hoodie off merchmarket last week and the quality is way better than i expected for the price",
    "status": "pending"
  }
]
```

### `data/state.json` (internal)
Replied comment IDs (with date), per-sub daily counters, last successful keyword-generation date.

## 7. Reply Style Rules (enforced in prompt + validated in code)

- **Exactly ONE sentence** — a long run-on sentence is fine and encouraged over multiple short ones; two or more terminal sentences = regenerate once, then log + skip if it happens again.
- ≤ ~40 words (`style.max_reply_words`, configurable).
- No links in v1; store name appears at most once, never as a URL.
- Acknowledge the commenter's actual point first (the conjoining factor), then the subtle product reference.
- Match the thread's register (casual sub = casual reply); no "OP" overuse; no exclamation-stacking.

## 8. Stealth Behavior (extension)

- **Human typing cadence** — per-character delays with jitter, micro-pauses at punctuation, focus the box before typing.
- **Randomized inter-post delay** — drawn from configured range (default 2–10 min); popup shows a visible countdown.
- **Real navigation** — each post happens on the actual thread page via permalink (full load + scroll-to-comment), never injected into stale DOM.
- **Preview mode** — fills every reply box without submitting; read in context, then flip to Post. Recommended for the first week of operation.

## 9. Error Handling

| Failure | Behavior |
|---|---|
| LM Studio down / model not loaded | Fail fast at preflight with clear message — no partial runs |
| Malformed inbox file | Report file + problem, skip it, process the rest |
| Keyword gen fails/empty | Fall back to last good list (warn in summary) |
| One reply gen fails | Log + skip that comment, batch continues |
| Comment ID not found on page | Entry marked `not_found`, queue pauses, popup identifies which entry |
| Reddit moderation hold ("post pending") | Detected via confirmation UI; entry marked `pending_moderation`; counts against cap either way |
| Double-run same day | State makes already-processed comments no-ops; summary says so |

## 10. Testing Strategy

- **Unit tests (offline, no LLM):** matcher edge cases (word boundaries, multi-word phrases, case), inbox parser vs fixture Web Scraper exports, config validation, state dedup/cap logic.
- **`python -m astroturf check`:** live smoke test — hits LM Studio, prints a sample keyword list and one sample reply for quality judgment before touching Reddit.
- **Fixture-driven LLM tests:** recorded responses let the generation pipeline be tested offline; live calls only in `check`.
- **Extension manual checklist:** documented steps (load file → preview on throwaway thread → verify typing/submit/delay behavior), run at install and after any extension change.
- **Go-live sequence:** dry-run week on one low-stakes sub with Preview-only, then first real posts under conservative caps.

## 11. Configuration & Targeting

- Standing target list in `config/subreddits.json` (per-sub: enabled flag, optional cap override).
- CLI override for one-off runs: `python -m astroturf run r/foo r/bar`.
- All stealth/style knobs are config values so the profile can be dialed up as the account ages.

## 12. Open Items

- **Astroturf account age** — unknown at design time; conservative defaults cover both fresh and aged accounts, caps tunable later.
- **Exact `catalog.json` shape** — produced by the user's existing cron (all categories + subcategories); the catalog adapter normalizes whatever fields it contains. Confirmed against a real sample during implementation.
- **Web Scraper rule setup** — documented in README with exact selectors for old-reddit hot pages; verified during implementation.
