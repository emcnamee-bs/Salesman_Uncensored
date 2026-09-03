from astroturf.inbox import CommentRecord
from astroturf.matcher import match_comments


def rec(body, comment_id="c1"):
    return CommentRecord(
        subreddit="r/spiderman",
        post_id="p1",
        post_title="t",
        comment_id=comment_id,
        author="a",
        score=0,
        body=body,
        permalink="",
    )


def test_single_word_requires_boundary():
    flagged = match_comments([rec("I love venom and symbiotes")], ["venom"])
    assert len(flagged) == 1
    assert flagged[0].matched_keywords == ["venom"]

    # "venom" must not match inside "symbiotevenom" or as a prefix of another word
    none = match_comments([rec("the symbiotevenom hybrid is cool")], ["venom"])
    assert none == []


def test_phrase_substring_match():
    flagged = match_comments(
        [rec("the black suit scene was insane")], ["black suit"]
    )
    assert len(flagged) == 1
    assert flagged[0].matched_keywords == ["black suit"]


def test_case_insensitive():
    flagged = match_comments([rec("BLACK SUIT forever")], ["black suit"])
    assert len(flagged) == 1


def test_multiple_keywords_recorded_in_order():
    flagged = match_comments(
        [rec("venom and the black suit are my favorites")],
        ["black suit", "venom"],
    )
    assert len(flagged) == 1
    assert flagged[0].matched_keywords == ["black suit", "venom"]


def test_unflagged_comments_dropped():
    out = match_comments([rec("totally unrelated cooking talk")], ["venom"])
    assert out == []


def test_keyword_with_regex_specials():
    flagged = match_comments([rec("the c++ meme shirt is great")], ["c++"])
    assert len(flagged) == 1
