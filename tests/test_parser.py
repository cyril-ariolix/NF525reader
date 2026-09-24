"""Tests for HTML journal parser."""

import re
from pathlib import Path

from src.parser.html_archive import H2_SPLIT_PATTERN, parse_journal

FIXTURES = Path(__file__).parent / "fixtures"


def test_h2_split_pattern_handles_attributes():
    text = '<h2 class="foo">Facture 09000001</h2><table></table>'
    parts = H2_SPLIT_PATTERN.split(text)
    assert len(parts) == 2
    assert "Facture 09000001" in parts[1]


def test_parse_daily_old_fixture():
    html = (FIXTURES / "daily_old.html").read_bytes()
    result = parse_journal(html)

    assert len(result.documents) == 3
    types = {doc.document_type for doc in result.documents}
    assert types == {"Facture", "Pro Forma"}

    facture1 = next(d for d in result.documents if d.document_number == "09000001")
    assert facture1.amount_ht_cents == 9015
    assert facture1.amount_ttc_cents == 10000
    assert facture1.amount_tva_cents == 985  # 818 + 167
    assert len(facture1.payments) == 2
    assert facture1.html_fragment.startswith("<h2")
    assert "class=\"foo\"" in facture1.html_fragment or "class='foo'" in facture1.html_fragment or "foo" in facture1.html_fragment

    facture2 = next(d for d in result.documents if d.document_number == "09000002")
    assert facture2.customer_name == "WEEKENDESK INDEX"
    assert facture2.amount_ttc_cents == 25000

    proforma = next(d for d in result.documents if d.document_number == "00001144")
    assert proforma.document_type == "Pro Forma"
    assert proforma.amount_ttc_cents == 5500

    assert result.hotel_header.display_name == "Test Hotel"
    assert result.section_counts.get("Grand Totals", 0) >= 1


def test_parse_daily_new_fixture():
    html = (FIXTURES / "daily_new.html").read_bytes()
    result = parse_journal(html)

    assert len(result.documents) == 2
    facture = next(d for d in result.documents if d.document_number == "09022192")
    note = next(d for d in result.documents if d.document_number == "00005691")

    assert facture.customer_name == "El Fadili, Nadia"
    assert facture.business_date == "2025-11-15"
    assert len(facture.payments) == 0
    assert facture.html_fragment.lower().startswith("<h2")

    assert note.document_type == "Note"
    assert note.amount_ttc_cents == 1100


def test_no_tickets_section():
    html = b"<html><body><h1>Grand Totals</h1></body></html>"
    result = parse_journal(html)
    assert len(result.documents) == 0
    assert any("No Tickets" in w for w in result.warnings)


def test_avoir_document_type():
    html = b"""<html><body>
    <h1>Tickets 2019-01-01</h1>
    <h2>Avoir 00000099</h2>
    <table><tr><th>Field</th><th>Value</th></tr>
    <tr><td>NF525TicketID</td><td>1</td></tr>
    <tr><td>TimeStamp</td><td>2019-01-01 10:00:00</td></tr>
    <tr><td>DocumentNumber</td><td>00000099</td></tr></table>
    <h2>Total</h2>
    <table><tr><th>TotalAmountExclVat</th><th>TotalAmountInclVat</th></tr>
    <tr><td>10,00</td><td>12,00</td></tr></table>
    <h1>Duplicates</h1>
    </body></html>"""
    result = parse_journal(html)
    assert len(result.documents) == 1
    assert result.documents[0].document_type == "Avoir"


def test_grand_totals_not_parsed_as_invoices():
    html = (FIXTURES / "daily_old.html").read_bytes()
    result = parse_journal(html)
    numbers = [d.document_number for d in result.documents]
    assert "210" not in numbers
