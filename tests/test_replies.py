from astroturf.config import Settings
from astroturf.inbox import CommentRecord
from astroturf.matcher import FlaggedComment
from astroturf.replies import ReplyEntry, generate_replies


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, system, user, model, temperature=0.7, max_tokens=512):
        self.calls += 1
        if not self.replies:
            raise RuntimeError("no canned replies left")
        return self.replies.pop(0)


def settings():
    return Settings(store_name="merchmarket", reply_model="small", max_reply_words=40, include_links=False)


ITEMS = [type("I", (), {"name": "Venom Hoodie", "category": "Superheroes", "subcategory": "Marvel", "description": ""})()]


def flagged(body="the black suit actually moves with him, wild"):
    c = CommentRecord(
        subreddit="r/spiderman", post_id="1abc", post_title="Black suit discussion",
        comment_id="xyz", author="fan", score=42, body=body,
        permalink="https://old.reddit.com/r/spiderman/comments/1abc/black_suit_discussion/t1_xyz/",
    )
    return FlaggedComment(comment=c, matched_keywords=["black suit"])


def test_generate_one_entry_with_contract_shape():
    client = FakeLLM(["honestly the black-suit hoodie i got off merchmarket after that scene is even better in person"])
    entries, skips = generate_replies(client, settings(), [flagged()], ITEMS)
    assert skips == []
    assert len(entries) == 1
    e = entries[0]
    d = e.to_dict()
    assert list(d.keys()) == [
        "subreddit", "post_id", "comment_id", "permalink",
        "matched_keywords", "comment_excerpt", "reply", "status",
    ]
    assert d["subreddit"] == "r/spiderman"
    assert d["comment_id"] == "xyz"
    assert d["matched_keywords"] == ["black suit"]
    assert d["status"] == "pending"
    assert "black suit actually moves with him" in d["comment_excerpt"]


def test_dry_run_sets_preview_status():
    client = FakeLLM(["picked up a black-suit hoodie off merchmarket and it slaps"])
    entries, _ = generate_replies(client, settings(), [flagged()], ITEMS, dry_run=True)
    assert entries[0].status == "preview"


def test_style_violation_regenerates_once():
    client = FakeLLM([
        "two sentences here. And a second one, honestly.",  # fails: two terminal runs
        "one long run-on sentence that works fine with the merchmarket hoodie reference inside it",
    ])
    entries, skips = generate_replies(client, settings(), [flagged()], ITEMS)
    assert client.calls == 2
    assert len(entries) == 1 and skips == []


def test_double_violation_skips_with_log():
    client = FakeLLM(["first one. second one.", "third one. fourth one."])
    entries, skips = generate_replies(client, settings(), [flagged()], ITEMS)
    assert entries == []
    assert len(skips) == 1
    assert "xyz" in skips[0] and "style" in skips[0].lower()


def test_llm_failure_skips_and_batch_continues():
    class FlakyLLM:
        calls = 0
        def chat(self, system, user, model, temperature=0.7, max_tokens=512):
            FlakyLLM.calls += 1
            if FlakyLLM.calls == 1:
                raise RuntimeError("model exploded")
            return "second comment reply that is fine"

    f = flagged(body="first comment body")
    g = flagged(body="second comment body about the black suit")
    g.comment.comment_id = "zzz"
    flaky = FlakyLLM()
    entries, skips = generate_replies(flaky, settings(), [f, g], ITEMS)
    assert len(entries) == 1 and entries[0].comment_id == "zzz"
    assert len(skips) == 1 and "xyz" in skips[0]


def test_excerpt_capped_at_200_chars():
    long_body = "x" * 500
    client = FakeLLM(["a fine one sentence reply about the merchmarket hoodie"])
    entries, _ = generate_replies(client, settings(), [flagged(body=long_body)], ITEMS)
    assert len(entries[0].comment_excerpt) == 200


def test_to_dict_roundtrip():
    e = ReplyEntry(
        subreddit="r/x", post_id="p", comment_id="c", permalink="https://old.reddit.com/r/x/comments/p/_/c/",
        matched_keywords=["k"], comment_excerpt="ex", reply="r", status="pending",
    )
    assert e.to_dict()["reply"] == "r"
