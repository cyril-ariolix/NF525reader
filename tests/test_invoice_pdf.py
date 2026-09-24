"""Tests for A4 invoice PDF generation."""

import re
import zlib
from pathlib import Path

from src.parser.html_archive import parse_journal
from src.ui.invoice_pdf import build_invoice_pdf, pdf_filename

FIXTURES = Path(__file__).parent / "fixtures"


def _invoice_from_fixture(doc_number: str = "09000001") -> dict:
    result = parse_journal((FIXTURES / "daily_old.html").read_bytes())
    doc = next(d for d in result.documents if d.document_number == doc_number)
    return {
        "hotel_code": "FR005082",
        "hotel_display_name": result.hotel_header.display_name,
        "document_type": doc.document_type,
        "document_number": doc.document_number,
        "business_date": doc.business_date,
        "issued_at": doc.issued_at,
        "nf525_ticket_id": doc.nf525_ticket_id,
        "customer_name": doc.customer_name,
        "customer_vat": doc.customer_vat,
        "amount_ht_cents": doc.amount_ht_cents,
        "amount_tva_cents": doc.amount_tva_cents,
        "amount_ttc_cents": doc.amount_ttc_cents,
        "vat_lines_json": doc.vat_lines_json,
        "html_fragment": doc.html_fragment,
        "payments": [
            {
                "payment_mode": p.payment_mode,
                "payment_method": p.payment_method,
                "amount_cents": p.amount_cents,
            }
            for p in doc.payments
        ],
    }


def test_build_invoice_pdf_starts_with_pdf_magic():
    pdf_bytes = build_invoice_pdf(_invoice_from_fixture())
    assert pdf_bytes.startswith(b"%PDF")


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    parts: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.DOTALL):
        data = match.group(1)
        try:
            parts.append(zlib.decompress(data).decode("cp1252", errors="replace"))
        except zlib.error:
            parts.append(data.decode("cp1252", errors="replace"))
    return "".join(parts)


def test_build_invoice_pdf_contains_document_number():
    invoice = _invoice_from_fixture("09000001")
    pdf_bytes = build_invoice_pdf(invoice)
    text = _extract_pdf_text(pdf_bytes)
    assert invoice["document_number"] in text
    assert "HEBERGEMENT - Chambre" in text
    assert "100,00 €" in text
    assert "?" not in text


def test_pdf_filename():
    name = pdf_filename("FR005081", "Facture", "09000001")
    assert name == "FR005081_Facture_09000001.pdf"
