import pytest

from services.common.subtitle.abbreviations import is_abbreviation, COMMON_ABBREVIATIONS


def test_is_abbreviation_recognizes_dr():
    assert is_abbreviation("Dr.") is True
    assert is_abbreviation("dr.") is True


def test_is_abbreviation_recognizes_us():
    assert is_abbreviation("U.S.") is True
    assert is_abbreviation("u.s.") is True


def test_is_abbreviation_rejects_normal_words():
    assert is_abbreviation("Hello") is False
    assert is_abbreviation("world.") is False


def test_is_abbreviation_handles_empty():
    assert is_abbreviation("") is False
    assert is_abbreviation(None) is False
