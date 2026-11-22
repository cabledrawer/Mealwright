"""Invisible control characters are refused in every name someone types, new and old
(security audit, 19 Oct): tabs and line breaks in a one-line field, and anything that
shows nothing or flips the order text is drawn in. One shared check, in mealwright.names.
"""

import sys
import time
import unicodedata
from typing import Any

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sync_kit import action, new_id, ok, send

from mealwright import names, page_reader
from mealwright.names import has_hidden, one_line, text_block, without_hidden

API = "/api/v1"

# What gets refused: a tab, a line break, NUL, an escape, a zero-width space, a
# right-to-left override, a byte-order mark, a line separator.
BAD = ["Toor\tdal", "Toor\ndal", "Toor\x00dal", "Toor\x1bdal", "Toor\u200bdal", "Toor\u202edal"]
BAD += ["\ufeffToor", "Toor\u2028dal", "Toor\rdal"]


def refused(response: Any) -> None:
    assert response.status_code == 422, response.text
    assert "hidden character" in response.text or "tab" in response.text, response.text


def test_the_shared_check() -> None:
    for text in BAD:
        assert has_hidden(text), repr(text)
        with pytest.raises(ValueError, match="hidden character"):
            one_line(text)
    # Plain text, accents, Tamil with its joiners, emoji with a joiner: all fine.
    for fine in ["Toor dal", "Jalapeño", "துவரம் பருப்பு", "ക്ക് ", "👩\u200d🍳 chef", "½ cup"]:
        assert not has_hidden(fine), repr(fine)
        assert one_line(fine) == fine


def test_text_blocks_may_keep_their_line_breaks() -> None:
    assert text_block("Fry.\nAdd salt.") == "Fry.\nAdd salt."
    assert text_block("Fry.\r\nAdd salt.") == "Fry.\nAdd salt."
    for bad in ["Fry\tit", "Fry\x00", "Fry\u202e", "Fry\rit", "Fry\u2028it"]:
        with pytest.raises(ValueError, match="hidden character"):
            text_block(bad)


@pytest.mark.parametrize("bad", BAD)
def test_ingredient_names_refuse_hidden_characters(kitchen: TestClient, bad: str) -> None:
    refused(kitchen.post(f"{API}/foods", json={"name": bad}))
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    url = f"{API}/foods/{food['id']}"
    refused(kitchen.patch(url, json={"name": bad}))  # renaming an old name
    refused(kitchen.patch(url, json={"count_word": bad}))
    refused(kitchen.post(f"{url}/other-names", json={"name": bad}))
    refused(kitchen.post(f"{url}/sizes", json={"name": bad, "amount": 500}))
    # Nothing was stored.
    assert ok(kitchen.get(url))["name"] == "Toor dal"
    assert ok(kitchen.get(url))["other_names"] == []
    assert ok(kitchen.get(url))["sizes"] == []


def test_size_names_and_answers_refuse_hidden_characters(kitchen: TestClient) -> None:
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    url = f"{API}/foods/{food['id']}"
    size = ok(kitchen.post(f"{url}/sizes", json={"name": "packet", "amount": 500}), 201)
    size_id = size["food"]["sizes"][0]["id"]
    refused(kitchen.patch(f"{url}/sizes/{size_id}", json={"name": "pack\tet"}))
    answer = {"kind": "size", "food_id": food["id"], "name": "lo\naf", "amount": 20}
    stock = {"food_id": food["id"], "amount": {"amount": 1, "unit": "loaf", "answers": [answer]}}
    refused(kitchen.post(f"{API}/stock", json=stock))


def test_whitespace_only_rename_is_a_plain_422_not_a_crash(kitchen: TestClient) -> None:
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    response = kitchen.patch(f"{API}/foods/{food['id']}", json={"name": "   "})
    assert response.status_code == 422, response.text


def test_shop_and_list_names_refuse_hidden_characters(kitchen: TestClient) -> None:
    refused(kitchen.post(f"{API}/shops", json={"name": "Spice\tBazaar"}))
    refused(kitchen.post(f"{API}/shopping/lists", json={"name": "Party\nlist"}))
    made = ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party"}), 201)
    list_id = made["shopping_list"]["id"]
    refused(kitchen.patch(f"{API}/shopping/lists/{list_id}", json={"name": "Par\u200bty"}))
    assert [s["name"] for s in ok(kitchen.get(f"{API}/shops"))["shops"]] == []


def test_the_offline_queue_refuses_hidden_characters_in_names(kitchen: TestClient) -> None:
    answer = send(kitchen, action("create_list", list_id=new_id(), name="Par\tty"))
    result = answer["results"][0]
    assert result["status"] == "refused" and result["reason"] == "bad_action", result
    assert "hidden character" in result["message"] or "tab" in result["message"]


def test_your_name_at_set_up_refuses_hidden_characters(client: TestClient) -> None:
    body = {**ADMIN, "name": "Kri\tshna"}
    refused(client.post(f"{API}/setup", json=body))
    body["name"] = "Tess"
    assert client.post(f"{API}/setup", json=body).status_code == 201


def test_old_names_still_read_fine(kitchen: TestClient) -> None:
    """A name stored before the check keeps working; only writing a new one is checked."""
    from mealwright.models import Food

    food = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.get(Food, food["id"]).name = "Old\tname"  # type: ignore[union-attr]
        db.commit()
    assert ok(kitchen.get(f"{API}/foods/{food['id']}"))["name"] == "Old\tname"
    # Renaming it to something clean works; to something with a hidden character doesn't.
    refused(kitchen.patch(f"{API}/foods/{food['id']}", json={"name": "New\tname"}))
    assert ok(kitchen.patch(f"{API}/foods/{food['id']}", json={"name": "New name"}))["food"]


# Written with chr() so the invisible ones can be seen in the code.
ZWNJ, ZWJ, RLO = chr(0x200C), chr(0x200D), chr(0x202E)
SCOTLAND = chr(0x1F3F4) + "".join(chr(0xE0000 + ord(c)) for c in "gbsct") + chr(0xE007F)
FAMILY = chr(0x1F468) + ZWJ + chr(0x1F469) + ZWJ + chr(0x1F467) + ZWJ + chr(0x1F466)
TAMIL_WITH_ZWNJ = "\u0b95\u0bcd" + ZWNJ + "\u0bb7"
MALAYALAM_WITH_ZWJ = "\u0d28\u0d4d" + ZWJ + " \u0d15\u0d4d" + ZWJ
HEART_AS_EMOJI = chr(0x2764) + chr(0xFE0F)  # a variation selector


def test_words_that_need_joiners_and_emoji_sequences_are_fine() -> None:
    for fine in [TAMIL_WITH_ZWNJ, MALAYALAM_WITH_ZWJ, FAMILY, SCOTLAND, HEART_AS_EMOJI]:
        assert not has_hidden(fine), fine.encode("unicode_escape")
        assert one_line(f"Dal {fine}") == f"Dal {fine}"
        assert text_block(f"Mix {fine}\nthen serve") == f"Mix {fine}\nthen serve"


def test_direction_overrides_and_isolates_are_refused_next_to_good_text() -> None:
    for bad_char in [RLO, chr(0x202A), chr(0x202D), chr(0x2066), chr(0x2069), chr(0x200E)]:
        for text in (f"Dal{bad_char}", f"{FAMILY}{bad_char}", f"{SCOTLAND}{bad_char}x"):
            assert has_hidden(text), text.encode("unicode_escape")


def test_good_words_work_in_real_names_and_a_flipped_name_does_not(kitchen: TestClient) -> None:
    for name in [f"Kheer {FAMILY}", f"Haggis {SCOTLAND}", f"Dal {TAMIL_WITH_ZWNJ}"]:
        ok(kitchen.post(f"{API}/foods", json={"name": name}), 201)
        ok(kitchen.post(f"{API}/recipes", json={"name": name, "tags": [name[:30]]}), 201)
    refused(kitchen.post(f"{API}/foods", json={"name": f"Dal {RLO}lad"}))
    refused(kitchen.post(f"{API}/recipes", json={"name": f"Dal {RLO}lad"}))


def flag(letters: str, end: bool = True) -> str:
    return (
        chr(0x1F3F4)
        + "".join(chr(0xE0000 + ord(c)) for c in letters)
        + (chr(0xE007F) if end else "")
    )


def test_flag_emoji_are_fine_and_tag_characters_anywhere_else_are_not() -> None:
    for fine in [
        SCOTLAND,
        flag("gbeng"),
        flag("gbwls"),
        f"Haggis {flag('gbsct')} and {flag('gbeng')}",
    ]:
        assert not has_hidden(fine), fine.encode("unicode_escape")
    tags = "".join(chr(0xE0000 + ord(c)) for c in "ignore this")
    for bad_text in [
        tags,  # hidden text with no flag in front
        "Dal " + tags,  # hidden ASCII-lookalike text after a normal word
        chr(0xE007F),  # a cancel tag alone
        flag("gbsct", end=False),  # a flag with no cancel tag at the end
        flag("gbsct", end=False) + "x",
        chr(0x1F3F4) + chr(0xE007F),  # a flag and cancel tag with no letters between
        flag("g"),  # one letter is too few
        flag("gbscotl"),  # seven letters are too many
        flag("a" * 40),
        flag("ignore previous instructions"),  # a sentence hidden inside a flag (tag spaces)
        flag("gb sct"),  # a tag space
        flag("GBSCT"),  # capitals are not region codes
        SCOTLAND + tags,  # a good flag, then hidden text
        "x" + chr(0xE0067),
    ]:
        assert has_hidden(bad_text), bad_text.encode("unicode_escape")
        with pytest.raises(ValueError, match="hidden character"):
            one_line(bad_text)


# --- cut_text keeps flags and skin tones whole (#55 round 2, L4) ---------------------------


def test_cut_text_does_not_split_a_country_flag() -> None:
    from mealwright.names import cut_text

    india = "\U0001f1ee\U0001f1f3"
    assert cut_text("ab" + india + "cd", 3) == "ab"  # not "ab" + the first letter
    assert cut_text("ab" + india + "cd", 4) == "ab" + india
    assert cut_text(india * 3, 3) == india  # two flags and a half: whole flags only


def test_cut_text_does_not_split_a_skin_tone() -> None:
    from mealwright.names import cut_text

    thumbs = "\U0001f44d\U0001f3fd"
    assert cut_text("ab" + thumbs, 3) == "ab"
    assert cut_text("ab" + thumbs, 4) == "ab" + thumbs


def test_cut_text_never_cuts_a_text_of_only_marks_to_empty() -> None:
    from mealwright.names import cut_text

    marks = "\u0301" * 10
    assert cut_text(marks, 4) == "\u0301" * 4


# --- The checks run in C (T4, 22 Nov) --------------------------------------------------------
# `has_hidden`, `without_hidden` and the page reader's `_strip_hidden` were one Python step
# per character; a 5 MB recipe field took seconds of CPU. They now use a regular expression
# and `str.translate`. These are the old loops, kept to show the answers didn't change.

_JOINERS = {"\u200c", "\u200d"}
_TAGS = (*range(0xE0030, 0xE003A), *range(0xE0061, 0xE007B))


def _old_flag_end(value: str, start: int) -> int:
    if ord(value[start]) != 0x1F3F4:
        return start
    end = start + 1
    while end < len(value) and ord(value[end]) in _TAGS:
        end += 1
    if 2 <= end - start - 1 <= 6 and end < len(value) and ord(value[end]) == 0xE007F:
        return end + 1
    return start


def _old_has_hidden(value: str, newlines: bool = False) -> bool:
    index = 0
    while index < len(value):
        char = value[index]
        end = _old_flag_end(value, index)
        if end > index:
            index = end
            continue
        index += 1
        if char in _JOINERS or (newlines and char == "\n"):
            continue
        if unicodedata.category(char) in ("Cc", "Cf", "Cs", "Zl", "Zp"):
            return True
    return False


def _old_without_hidden(value: str, breaks: str | None = None) -> str:
    """`names.without_hidden`, or with `breaks` the page reader's `_strip_hidden` (those
    become a space and a line break stays)."""
    kept: list[str] = []
    index = 0
    while index < len(value):
        end = _old_flag_end(value, index)
        if end > index:
            kept.append(value[index:end])
            index = end
            continue
        char = value[index]
        index += 1
        if breaks is not None:
            if char in breaks:
                kept.append(" ")
            elif char == "\n" or not _old_has_hidden(char):
                kept.append(char)
        elif char == "\r":
            if value[index : index + 1] == "\n":
                index += 1
            kept.append("\n")
        elif char in "\n\u2028\u2029\x0b\x0c\x85":
            kept.append("\n")
        elif char == "\t":
            kept.append(" ")
        elif char in _JOINERS or unicodedata.category(char) not in ("Cc", "Cf", "Cs", "Zl", "Zp"):
            kept.append(char)
    return "".join(kept)


# Plain letters, every kind of hidden character, the joiners, the black flag, tag letters,
# the cancel tag, other tag characters, surrogates, emoji, and any character at all.
_TRICKY = st.sampled_from(
    [
        *"ab \n\r\t\x00\x0b\x0c\x85\u2028\u2029\u200b\u200c\u200d\u202e\u2066\ufeff\u00ad",
        *("\U0001f3f4", "\U000e0067", "\U000e0062", "\U000e0073", "\U000e0031", "\U000e007f"),
        *("\U000e0001", "\U000e0020", "\ud800", "\udfff", "\U0001f600", "\u0301"),
    ]
)
_TEXT = st.lists(st.one_of(_TRICKY, _TRICKY, st.characters()), max_size=40).map("".join)
_SCOTLAND = "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"


@settings(max_examples=3000, deadline=None)
@given(_TEXT)
def test_the_fast_checks_give_the_old_answers(value: str) -> None:
    for text in (value, _SCOTLAND + value, value + _SCOTLAND + value):
        assert has_hidden(text) == _old_has_hidden(text), repr(text)
        assert has_hidden(text, newlines=True) == _old_has_hidden(text, newlines=True)
        assert without_hidden(text) == _old_without_hidden(text), repr(text)
        assert page_reader._strip_hidden(text) == _old_without_hidden(
            text, page_reader._WHITESPACE_BREAKS
        ), repr(text)


def test_every_hidden_character_is_found_as_before() -> None:
    for code in range(sys.maxunicode + 1):
        char = chr(code)
        assert has_hidden("a" + char) == _old_has_hidden("a" + char), hex(code)
        assert has_hidden(char, newlines=True) == _old_has_hidden(char, newlines=True)


def test_hidden_characters_are_only_in_the_planes_searched() -> None:
    """The table is made from three planes only (T4 security pass r1: each page read starts
    a fresh Python); a Python with newer Unicode data that adds one elsewhere fails here."""
    everywhere = {
        chr(code)
        for code in range(sys.maxunicode + 1)
        if unicodedata.category(chr(code)) in ("Cc", "Cf", "Cs", "Zl", "Zp")
    } - {"\u200c", "\u200d"}
    assert names._hidden_characters() == everywhere


@pytest.mark.parametrize("filler", ["1", "\u200b", "\U0001f3f4", _SCOTLAND, "\r\n\t"])
def test_a_page_sized_text_is_checked_quickly(filler: str) -> None:
    text = filler * (5_000_000 // len(filler))
    has_hidden("")  # the tables are made on first use
    start = time.process_time()
    has_hidden(text)
    has_hidden(text, newlines=True)
    without_hidden(text)
    page_reader._strip_hidden(text)
    assert time.process_time() - start < 2
