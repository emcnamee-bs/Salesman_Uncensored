import json
from datetime import date

import pytest

from astroturf.config import Settings
from astroturf.keywords import KeywordGenerationError, ensure_keywords, extract_json_array


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def chat(self, system, user, model, temperature=0.7, max_tokens=512):
        self.calls += 1
        return self.reply


def settings():
    return Settings(keyword_model="big", reply_model="small")


ITEMS = [type("I", (), {"name": "Venom Hoodie", "category": "Superheroes", "subcategory": "Marvel", "description": ""})()]


def test_extract_plain_array():
    assert extract_json_array('["venom", "symbiote"]') == ["venom", "symbiote"]


def test_extract_from_markdown_fence_and_prose():
    text = 'Here you go:\n```json\n["black suit", "venom symbiote"]\n```\nHope that helps!'
    assert extract_json_array(text) == ["black suit", "venom symbiote"]


def test_extract_dedups_and_strips():
    assert extract_json_array('["a", " a ", "b", 3, null]') == ["a", "b"]


def test_extract_no_array_raises():
    with pytest.raises(KeywordGenerationError):
        extract_json_array("no json here")


def test_ensure_keywords_generates_and_saves(tmp_path):
    client = FakeLLM('["venom", "symbiote black suit"]')
    kws, source = ensure_keywords(client, settings(), ITEMS, tmp_path, today=date(2026, 9, 2))
    assert kws == ["venom", "symbiote black suit"]
    assert source == "generated"
    saved = json.loads((tmp_path / "keywords-2026-09-02.json").read_text())
    assert saved["date"] == "2026-09-02"
    assert saved["model"] == "big"
    assert saved["keywords"] == kws


def test_ensure_keywords_cached_same_day(tmp_path):
    (tmp_path / "keywords-2026-09-02.json").write_text(
        json.dumps({"date": "2026-09-02", "model": "big", "keywords": ["cached kw"]})
    )
    client = FakeLLM('["should not be used"]')
    kws, source = ensure_keywords(client, settings(), ITEMS, tmp_path, today=date(2026, 9, 2))
    assert kws == ["cached kw"]
    assert source == "cached"
    assert client.calls == 0


def test_ensure_keywords_fallback_on_empty_generation(tmp_path):
    (tmp_path / "keywords-2026-09-01.json").write_text(
        json.dumps({"date": "2026-09-01", "model": "big", "keywords": ["old kw"]})
    )
    client = FakeLLM("the model rambled without any array")
    kws, source = ensure_keywords(client, settings(), ITEMS, tmp_path, today=date(2026, 9, 2))
    assert kws == ["old kw"]
    assert source == "fallback"


def test_ensure_keywords_no_list_anywhere_raises(tmp_path):
    client = FakeLLM("no array in sight")
    with pytest.raises(KeywordGenerationError):
        ensure_keywords(client, settings(), ITEMS, tmp_path, today=date(2026, 9, 2))
