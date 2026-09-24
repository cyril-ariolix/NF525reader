"""Tests for printable HTML generation."""

from src.ui.format import format_euros
from src.ui.print_html import (
    build_printable_html,
    download_filename,
    sanitize_fragment,
)


def test_sanitize_removes_script_and_onclick():
    fragment = (
        '<h2>Facture 09000001</h2>'
        '<table><tr><td onclick="alert(1)">90,00</td></tr></table>'
        '<script>alert("x")</script>'
    )
    safe = sanitize_fragment(fragment)
    assert "<script>" not in safe
    assert "onclick" not in safe
    assert "Facture 09000001" in safe
    assert "90,00" in safe


def test_build_printable_html_structure():
    html = build_printable_html(
        title="Test — Facture 09000001",
        html_fragment="<h2>Facture 09000001</h2><table><tr><td>100,00</td></tr></table>",
    )
    assert "@page" in html
    assert "@media print" in html
    assert "noprint" in html
    assert "charset=\"UTF-8\"" in html or "charset=UTF-8" in html
    assert "Imprimer / Enregistrer en PDF" in html
    assert "Facture 09000001" in html


def test_format_euros():
    assert format_euros(123456) == "1 234,56 €"
    assert format_euros(None) == "—"


def test_download_filename():
    name = download_filename("FR005081", "Facture", "09000001")
    assert name == "FR005081_Facture_09000001.html"
