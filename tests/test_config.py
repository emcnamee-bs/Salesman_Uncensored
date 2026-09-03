import json

import pytest

from astroturf.config import (
    ConfigError,
    load_settings,
    load_subreddits,
    normalize_subreddit,
)


def write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


SETTINGS = {
    "store_name": "merchmarket",
    "lmstudio": {
        "base_url": "http://localhost:1234/v1",
        "keyword_model": "qwen2.5-14b-instruct",
        "reply_model": "qwen2.5-7b-instruct",
    },
    "limits": {
        "max_replies_per_day": 5,
        "max_replies_per_sub_per_day": 2,
        "min_delay_seconds": 120,
        "max_delay_seconds": 600,
    },
    "style": {"include_links": False, "max_reply_words": 40},
}


def test_load_settings_full(tmp_path):
    p = write(tmp_path / "settings.json", SETTINGS)
    s = load_settings(p)
    assert s.store_name == "merchmarket"
    assert s.lmstudio_base_url == "http://localhost:1234/v1"
    assert s.keyword_model == "qwen2.5-14b-instruct"
    assert s.reply_model == "qwen2.5-7b-instruct"
    assert s.max_replies_per_day == 5
    assert s.max_replies_per_sub_per_day == 2
    assert s.min_delay_seconds == 120
    assert s.max_delay_seconds == 600
    assert s.include_links is False
    assert s.max_reply_words == 40
    assert s.max_comments_per_sub == 100


def test_load_settings_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "nope.json")


def test_load_settings_bad_json(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="valid JSON"):
        load_settings(p)


def test_load_settings_requires_models(tmp_path):
    raw = dict(SETTINGS)
    raw["lmstudio"] = {"base_url": "http://localhost:1234/v1", "keyword_model": "", "reply_model": ""}
    p = write(tmp_path / "settings.json", raw)
    with pytest.raises(ConfigError, match="keyword_model"):
        load_settings(p)


def test_load_settings_delay_order(tmp_path):
    raw = json.loads(json.dumps(SETTINGS))
    raw["limits"]["min_delay_seconds"] = 900
    p = write(tmp_path / "settings.json", raw)
    with pytest.raises(ConfigError, match="min_delay_seconds"):
        load_settings(p)


def test_normalize_subreddit():
    assert normalize_subreddit("spiderman") == "r/spiderman"
    assert normalize_subreddit("R/Venom ") == "r/venom"
    assert normalize_subreddit("r/marvel") == "r/marvel"


def test_load_subreddits_mixed_shapes(tmp_path):
    p = write(
        tmp_path / "subreddits.json",
        [
            {"subreddit": "spiderman", "enabled": True},
            {"subreddit": "venom", "enabled": False, "max_replies_per_sub_per_day": 1},
            "marvel",
        ],
    )
    subs = load_subreddits(p)
    assert [s.subreddit for s in subs] == ["r/spiderman", "r/venom", "r/marvel"]
    assert subs[0].enabled is True
    assert subs[1].enabled is False
    assert subs[1].max_replies_per_sub_per_day == 1
    assert subs[2].enabled is True
    assert subs[2].max_replies_per_sub_per_day is None


def test_load_subreddits_bad_entry(tmp_path):
    p = write(tmp_path / "subreddits.json", [{"name": "spiderman"}])
    with pytest.raises(ConfigError, match="entry 0"):
        load_subreddits(p)
