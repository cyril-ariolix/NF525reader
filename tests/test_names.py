"""Tests for archive filename parsing."""

import pytest

from src.ingestion.names import parse_nested_member, parse_root_filename


def test_parse_root_renoir():
    info = parse_root_filename("ExportNF525_HotelRenoirCannes_FR005081.zip")
    assert info.slug == "HotelRenoirCannes"
    assert info.code == "FR005081"


def test_parse_nested_daily_range_one_day():
    info = parse_nested_member("ExportNF525/NF525CashData_20181107_20181108.zip")
    assert info.kind == "daily"
    assert info.precedence == 1
    assert info.period_start == "2018-11-07"
    assert info.period_end == "2018-11-08"


def test_parse_nested_multi_year_range():
    info = parse_nested_member("ExportNF525/NF525CashData_20150915_20181107.zip")
    assert info.kind == "range"
    assert info.precedence == 2


def test_parse_nested_monthly():
    info = parse_nested_member("ExportNF525/NF525CashData_201811_Monthly.zip")
    assert info.kind == "monthly"
    assert info.precedence == 3
    assert info.period_start == "2018-11-01"
    assert info.period_end == "2018-11-30"


def test_parse_nested_mois():
    info = parse_nested_member("ExportNF525/NF525CashData_202506_Mois.zip")
    assert info.kind == "mois"
    assert info.precedence == 3


def test_parse_nested_annee():
    info = parse_nested_member("ExportNF525/NF525CashData_202501_Année.zip")
    assert info.kind == "annee"
    assert info.precedence == 4


def test_parse_nested_daily_hhmm():
    info = parse_nested_member("ExportNF525/NF525CashData_20190508_0452.zip")
    assert info.kind == "daily"
    assert info.precedence == 1
    assert info.period_start == "2019-05-08"


def test_parse_root_invalid():
    with pytest.raises(ValueError):
        parse_root_filename("not_a_valid_archive.zip")
