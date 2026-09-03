import json

from astroturf.inbox import parse_inbox


def write_json(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


PERMALINK = "https://old.reddit.com/r/spiderman/comments/1abc/black_suit_discussion/t1_xyz/"


def test_parse_web_scraper_export(tmp_path):
    write_json(
        tmp_path / "spiderman.json",
        [
            {
                "comment_id": "xyz",
                "body": "the black suit actually moves with him, wild",
                "author": "fan123",
                "score": 42,
                "permalink": PERMALINK,
                "post_title": "Black suit discussion",
            },
        ],
    )
    records, warnings = parse_inbox(tmp_path)
    assert warnings == []
    assert len(records) == 1
    r = records[0]
    assert r.subreddit == "r/spiderman"
    assert r.post_id == "1abc"
    assert r.comment_id == "xyz"
    assert r.author == "fan123"
    assert r.score == 42
    assert r.body.startswith("the black suit")


def test_parse_aliases_and_relative_permalink(tmp_path):
    write_json(
        tmp_path / "venom.json",
        [
            {
                "id": "abc123",
                "text": "symbiote lore is the best part",
                "user": "lorekeeper",
                "points": 7,
                "link": "/r/venom/comments/1def/symbiote_101/t1_abc123/",
            }
        ],
    )
    records, warnings = parse_inbox(tmp_path)
    assert len(records) == 1
    r = records[0]
    assert r.comment_id == "abc123"
    assert r.subreddit == "r/venom"
    assert r.post_id == "1def"
    assert r.score == 7
    assert r.permalink.startswith("https://")


def test_parse_wrapped_results_and_single_dict(tmp_path):
    write_json(
        tmp_path / "wrapped.json",
        {"results": [{"id": "w1", "text": "hello world", "link": "/r/marvel/comments/1ghi/x/t1_w1/"}]},
    )
    write_json(
        tmp_path / "single.json",
        {"id": "s1", "text": "solo comment", "link": "/r/dc/comments/1jkl/y/t1_s1/"},
    )
    records, warnings = parse_inbox(tmp_path)
    ids = [r.comment_id for r in records]
    assert "w1" in ids and "s1" in ids


def test_dedup_by_comment_id(tmp_path):
    write_json(
        tmp_path / "a.json",
        [{"id": "dup", "text": "first version", "link": "/r/x/comments/1aa/a/t1_dup/"}],
    )
    write_json(
        tmp_path / "b.json",
        [{"id": "dup", "text": "second version", "link": "/r/x/comments/1bb/b/t1_dup/"}],
    )
    records, warnings = parse_inbox(tmp_path)
    assert len(records) == 1
    assert records[0].body == "first version"


def test_malformed_file_warns_and_others_continue(tmp_path):
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    write_json(
        tmp_path / "good.json",
        [{"id": "g1", "text": "fine comment", "link": "/r/y/comments/1cc/c/t1_g1/"}],
    )
    records, warnings = parse_inbox(tmp_path)
    assert len(records) == 1
    assert any("bad.json" in w for w in warnings)


def test_record_without_id_or_permalink_warns(tmp_path):
    write_json(tmp_path / "noid.json", [{"text": "no id anywhere"}])
    records, warnings = parse_inbox(tmp_path)
    assert records == []
    assert any("noid.json" in w for w in warnings)


def test_missing_dir_returns_empty(tmp_path):
    records, warnings = parse_inbox(tmp_path / "does-not-exist")
    assert records == [] and warnings == []
