import json

from astroturf.state import State, load_state, save_state


def test_missing_file_is_empty(tmp_path):
    s = load_state(tmp_path / "state.json")
    assert s.already_replied("x") is False
    assert s.global_count("2026-09-02") == 0
    assert s.sub_count("2026-09-02", "r/foo") == 0


def test_mark_replied_increments_both_counters(tmp_path):
    path = tmp_path / "state.json"
    s = load_state(path)
    s.mark_replied("c1", "r/foo", "2026-09-02")
    s.mark_replied("c2", "r/foo", "2026-09-02")
    s.mark_replied("c3", "r/bar", "2026-09-02")
    save_state(s, path)

    reloaded = load_state(path)
    assert reloaded.already_replied("c1") is True
    assert reloaded.global_count("2026-09-02") == 3
    assert reloaded.sub_count("2026-09-02", "r/foo") == 2
    assert reloaded.sub_count("2026-09-02", "r/bar") == 1


def test_counts_are_per_day(tmp_path):
    path = tmp_path / "state.json"
    s = load_state(path)
    s.mark_replied("c1", "r/foo", "2026-09-01")
    save_state(s, path)

    reloaded = load_state(path)
    assert reloaded.global_count("2026-09-02") == 0
    assert reloaded.sub_count("2026-09-02", "r/foo") == 0
    assert reloaded.already_replied("c1") is True


def test_mark_replied_idempotent_per_comment(tmp_path):
    s = State()
    s.mark_replied("c1", "r/foo", "2026-09-02")
    s.mark_replied("c1", "r/foo", "2026-09-02")
    assert s.global_count("2026-09-02") == 1


def test_roundtrip_preserves_shape(tmp_path):
    path = tmp_path / "state.json"
    s = State()
    s.mark_replied("c1", "r/foo", "2026-09-02")
    save_state(s, path)
    raw = json.loads(path.read_text())
    assert set(raw.keys()) == {"replied", "daily_counts"}
    assert raw["replied"]["c1"] == {"date": "2026-09-02", "subreddit": "r/foo"}
