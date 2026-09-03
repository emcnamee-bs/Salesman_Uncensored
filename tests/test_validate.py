from astroturf.config import Settings
from astroturf.validate import validate_reply


def settings(**kw):
    base = dict(
        store_name="merchmarket",
        max_reply_words=40,
        include_links=False,
    )
    base.update(kw)
    return Settings(**base)


GOOD = "the way it clings to him is wild, honestly picked up a black-suit hoodie off merchmarket last week and the quality surprised me"


def test_good_reply_passes():
    ok, reason = validate_reply(GOOD, settings())
    assert ok, reason


def test_empty_fails():
    ok, reason = validate_reply("   ", settings())
    assert not ok and "empty" in reason


def test_two_sentences_fail():
    ok, reason = validate_reply("cool point. i got the hoodie, man.", settings())
    assert not ok and "sentence" in reason


def test_run_on_with_multiple_exclamations_is_one_sentence():
    ok, reason = validate_reply(
        "wow!! that scene is insane and honestly the merchmarket hoodie i grabbed after it is even better in person",
        settings(),
    )
    assert ok, reason


def test_question_mark_counts_as_terminal():
    ok, reason = validate_reply("isnt that the symbiote? anyway cool shirt.", settings())
    assert not ok and "sentence" in reason


def test_word_cap_enforced():
    long_reply = " ".join(["word"] * 41) + "."
    ok, reason = validate_reply(long_reply, settings(max_reply_words=40))
    assert not ok and "words" in reason

    ok2, _ = validate_reply(" ".join(["word"] * 40) + ".", settings(max_reply_words=40))
    assert ok2


def test_links_blocked_by_default():
    ok, reason = validate_reply(
        "check this out https://merchmarket.example.com its great", settings()
    )
    assert not ok and "link" in reason

    ok2, _ = validate_reply("check this out https://x.example it is great", settings(include_links=True))
    assert ok2


def test_store_name_at_most_once():
    ok, reason = validate_reply(
        "merchmarket has the shirt and merchmarket also has the hoodie", settings()
    )
    assert not ok and "store name" in reason

    ok2, _ = validate_reply("picked up a hoodie from merchmarket last week", settings())
    assert ok2


def test_store_name_case_insensitive():
    ok, reason = validate_reply(
        "MerchMarket is cool and MERCHMARKET again", settings()
    )
    assert not ok and "store name" in reason
