import pytest

from sahighar.privacy import PrivacyKeyMissing, tokenize


def test_the_same_value_gives_the_same_token_so_records_can_be_matched(monkeypatch):
    monkeypatch.setenv("SAHIGHAR_PII_KEY", "key-one")
    assert tokenize("pan", "ABCDE1234F") == tokenize("pan", " abcde1234f ")  # case and spacing do not matter
    assert tokenize("pan", "ABCDE1234F") != tokenize("pan", "ABCDE1234G")


def test_a_token_never_contains_the_value_and_kinds_do_not_collide(monkeypatch):
    monkeypatch.setenv("SAHIGHAR_PII_KEY", "key-one")
    token = tokenize("pan", "ABCDE1234F")
    assert "ABCDE1234F" not in token and token.startswith("pan:")
    assert tokenize("name", "ABCDE1234F") != token


def test_a_different_key_gives_different_tokens_so_a_leaked_database_cannot_be_reversed_by_guessing(monkeypatch):
    monkeypatch.setenv("SAHIGHAR_PII_KEY", "key-one")
    first = tokenize("pan", "ABCDE1234F")
    monkeypatch.setenv("SAHIGHAR_PII_KEY", "key-two")
    assert tokenize("pan", "ABCDE1234F") != first


def test_names_are_matched_ignoring_case_spacing_and_punctuation(monkeypatch):
    monkeypatch.setenv("SAHIGHAR_PII_KEY", "key-one")
    assert tokenize("name", "Ramesh  Shah") == tokenize("name", "RAMESH SHAH.")


def test_no_key_is_an_error_not_a_silent_fallback(monkeypatch):
    monkeypatch.delenv("SAHIGHAR_PII_KEY", raising=False)
    with pytest.raises(PrivacyKeyMissing, match="SAHIGHAR_PII_KEY"):
        tokenize("pan", "ABCDE1234F")
