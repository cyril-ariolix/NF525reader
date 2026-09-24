"""Tests for French money parsing."""

from src.parser.money import parse_cents


def test_parse_cents_with_spaces():
    assert parse_cents("1 234,56") == 123456


def test_parse_cents_simple():
    assert parse_cents("90,91") == 9091


def test_parse_cents_negative():
    assert parse_cents("-10,00") == -1000


def test_parse_cents_empty():
    assert parse_cents("") is None
    assert parse_cents(None) is None


def test_parse_cents_dot_decimal():
    assert parse_cents("1234.56") == 123456
