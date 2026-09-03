import json
from datetime import date
from pathlib import Path

from astroturf.cli import run_pipeline
from astroturf.config import SubTarget


class FakeLLM:
    def __init__(self):
        self.calls = []

    def models(self):
        return ["big", "small"]

    def chat(self, system, user, model, temperature=0.7, max_tokens=512):
        self.calls.append(model)
        if model == "big":
            return '["black suit", "venom"]'
        # reply model: always a valid one-sentence reply under 40 words
        return "that scene is wild and the black-suit hoodie i grabbed off merchmarket after it is even better in person"


def build_repo(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "catalog").mkdir()
    (tmp_path / "inbox").mkdir()
    (tmp_path / "out").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "config" / "settings.json").write_text(json.dumps({
        "store_name": "merchmarket",
        "lmstudio": {"base_url": "http://localhost:1234/v1", "keyword_model": "big", "reply_model": "small"},
        "limits": {"max_replies_per_day": 5, "max_replies_per_sub_per_day": 2, "min_delay_seconds": 120, "max_delay_seconds": 600},
        "style": {"include_links": False, "max_reply_words": 40},
    }))
    (tmp_path / "config" / "subreddits.json").write_text(json.dumps([
        {"subreddit": "spiderman", "enabled": True}
    ]))
    (tmp_path / "catalog" / "catalog.json").write_text(json.dumps(
        [{"name": "Venom Hoodie", "category": "Superheroes"}, {"name": "Spiderman Tee", "category": "Superheroes"}]
    ))
    (tmp_path / "inbox" / "spiderman.json").write_text(json.dumps([
        {
            "id": "c1",
            "text": "the black suit actually moves with him, wild",
            "link": "/r/spiderman/comments/1abc/black_suit/t1_c1/",
        },
        {
            "id": "c2",
            "text": "venom is my favorite character honestly",
            "link": "/r/spiderman/comments/1def/venom_talk/t1_c2/",
        },
        {
            "id": "c3",
            "text": "totally unrelated cooking talk",
            "link": "/r/spiderman/comments/1ghi/cooking/t1_c3/",
        },
    ]))


def test_end_to_end_run(tmp_path):
    build_repo(tmp_path)
    from astroturf.config import load_settings, load_subreddits

    settings = load_settings(tmp_path / "config" / "settings.json")
    targets = load_subreddits(tmp_path / "config" / "subreddits.json")
    client = FakeLLM()
    summary = run_pipeline(settings, targets, client, tmp_path, today=date(2026, 9, 2))

    assert summary["keywords_source"] == "generated"
    assert summary["comments_parsed"] == 3
    assert summary["flagged"] == 2
    assert summary["skipped_replied"] == 0
    assert summary["skipped_cap"] == 0
    assert summary["generated"] == 2

    replies = json.loads((tmp_path / "out" / "replies-2026-09-02.json").read_text())
    assert len(replies) == 2
    assert all(r["status"] == "pending" for r in replies)
    assert {r["comment_id"] for r in replies} == {"c1", "c2"}

    state = json.loads((tmp_path / "data" / "state.json").read_text())
    assert set(state["replied"].keys()) == {"c1", "c2"}
    assert state["daily_counts"]["2026-09-02"]["global"] == 2


def test_dry_run_writes_preview_and_no_state(tmp_path):
    build_repo(tmp_path)
    from astroturf.config import load_settings, load_subreddits

    settings = load_settings(tmp_path / "config" / "settings.json")
    targets = load_subreddits(tmp_path / "config" / "subreddits.json")
    summary = run_pipeline(settings, targets, FakeLLM(), tmp_path, today=date(2026, 9, 2), dry_run=True)

    assert summary["generated"] == 2
    replies = json.loads((tmp_path / "out" / "replies-2026-09-02.json").read_text())
    assert all(r["status"] == "preview" for r in replies)
    assert not (tmp_path / "data" / "state.json").exists()


def test_second_run_same_day_is_noop(tmp_path):
    build_repo(tmp_path)
    from astroturf.config import load_settings, load_subreddits

    settings = load_settings(tmp_path / "config" / "settings.json")
    targets = load_subreddits(tmp_path / "config" / "subreddits.json")
    run_pipeline(settings, targets, FakeLLM(), tmp_path, today=date(2026, 9, 2))
    summary2 = run_pipeline(settings, targets, FakeLLM(), tmp_path, today=date(2026, 9, 2))

    assert summary2["skipped_replied"] == 2
    assert summary2["generated"] == 0


def test_per_sub_cap_enforced_pre_generation(tmp_path):
    build_repo(tmp_path)
    from astroturf.config import load_settings, load_subreddits

    settings = load_settings(tmp_path / "config" / "settings.json")
    targets = [SubTarget(subreddit="r/spiderman", enabled=True, max_replies_per_sub_per_day=1)]
    summary = run_pipeline(settings, targets, FakeLLM(), tmp_path, today=date(2026, 9, 2))

    assert summary["generated"] == 1
    assert summary["skipped_cap"] == 1


def test_disabled_target_ignored(tmp_path):
    build_repo(tmp_path)
    from astroturf.config import load_settings

    settings = load_settings(tmp_path / "config" / "settings.json")
    targets = [SubTarget(subreddit="r/spiderman", enabled=False)]
    summary = run_pipeline(settings, targets, FakeLLM(), tmp_path, today=date(2026, 9, 2))
    assert summary["comments_parsed"] == 3  # parsed from inbox...
    assert summary["flagged"] == 0          # ...but none in enabled targets


def test_preflight_fails_when_model_missing(tmp_path):
    build_repo(tmp_path)
    from astroturf.config import load_settings, load_subreddits

    settings = load_settings(tmp_path / "config" / "settings.json")
    targets = load_subreddits(tmp_path / "config" / "subreddits.json")

    class OnlyBig(FakeLLM):
        def models(self):
            return ["big"]

    try:
        run_pipeline(settings, targets, OnlyBig(), tmp_path, today=date(2026, 9, 2))
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "small" in str(e)
