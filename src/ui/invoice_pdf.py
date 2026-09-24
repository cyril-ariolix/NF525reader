"""Generate A4 PDF invoices from stored NF525 invoice rows."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup
from fpdf import FPDF

from src.ui.format import format_euros

PAGE_WIDTH_MM = 210
PAGE_HEIGHT_MM = 297
MARGIN_MM = 15
CONTENT_WIDTH_MM = PAGE_WIDTH_MM - 2 * MARGIN_MM


@dataclass(frozen=True)
class LineItem:
    designation: str
    quantity: str


def build_invoice_pdf(invoice: dict[str, Any]) -> bytes:
    """Build a single-page (or multi-page) A4 PDF for one invoice."""
    fields = _parse_field_table(invoice.get("html_fragment", ""))
    line_items = _parse_line_items(invoice.get("html_fragment", ""))
    vat_lines = _parse_vat_lines(invoice.get("vat_lines_json", "[]"))

    pdf = FPDF(unit="mm", format="A4")
    pdf.core_fonts_encoding = "cp1252"
    pdf.set_margins(MARGIN_MM, MARGIN_MM, MARGIN_MM)
    pdf.set_auto_page_break(auto=True, margin=MARGIN_MM)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)

    y = MARGIN_MM
    y = _draw_letterhead(pdf, invoice, fields, y)
    y = _draw_title_block(pdf, invoice, y)
    y = _draw_client_box(pdf, invoice, y)
    y = _draw_line_items(pdf, line_items, y)
    y = _draw_vat_recap(pdf, vat_lines, y)
    y = _draw_totals(pdf, invoice, y)
    y = _draw_payments(pdf, invoice.get("payments") or [], y)
    _draw_footer(pdf, invoice)

    output = pdf.output()
    return bytes(output)


def pdf_filename(code: str, document_type: str, document_number: str) -> str:
    safe_type = re.sub(r"[^\w\s-]", "", document_type).strip().replace(" ", "_")
    return f"{code}_{safe_type}_{document_number}.pdf"


def _parse_field_table(fragment: str) -> dict[str, str]:
    soup = BeautifulSoup(fragment or "", "html.parser")
    for table in soup.find_all("table"):
        headers = _table_headers(table)
        if headers[:2] == ["Field", "Value"]:
            return _table_to_kv(table)
    return {}


def _parse_line_items(fragment: str) -> list[LineItem]:
    soup = BeautifulSoup(fragment or "", "html.parser")
    items: list[LineItem] = []
    for table in soup.find_all("table"):
        headers = _table_headers(table)
        if "ProductLabel" not in headers:
            continue
        label_idx = headers.index("ProductLabel")
        desc_idx = headers.index("Description") if "Description" in headers else None
        qty_idx = headers.index("Quantity") if "Quantity" in headers else None
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= label_idx:
                continue
            label = _cell_text(cells[label_idx])
            description = (
                _cell_text(cells[desc_idx])
                if desc_idx is not None and len(cells) > desc_idx
                else ""
            )
            quantity = (
                _cell_text(cells[qty_idx])
                if qty_idx is not None and len(cells) > qty_idx
                else ""
            )
            designation = label
            if description and description != label:
                designation = f"{label} - {description}"
            if designation:
                items.append(LineItem(designation=designation, quantity=quantity))
    return items


def _parse_vat_lines(vat_lines_json: str) -> list[dict[str, Any]]:
    try:
        lines = json.loads(vat_lines_json or "[]")
    except json.JSONDecodeError:
        return []
    return lines if isinstance(lines, list) else []


def _draw_letterhead(
    pdf: FPDF,
    invoice: dict[str, Any],
    fields: dict[str, str],
    y: float,
) -> float:
    display_name = (
        invoice.get("hotel_display_name")
        or fields.get("CompanyName")
        or invoice.get("hotel_code")
        or ""
    )
    legal_name = fields.get("CompanyName", "")
    address_parts = [
        fields.get("Address", ""),
        " ".join(
            part
            for part in (fields.get("ZipCode", ""), fields.get("City", ""))
            if part
        ),
        fields.get("Country", ""),
    ]
    siret = fields.get("Siret", "")
    vat = fields.get("VATNumber", "")

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_xy(MARGIN_MM, y)
    pdf.multi_cell(CONTENT_WIDTH_MM, 6, _latin1(display_name))
    y = pdf.get_y() + 1

    pdf.set_font("Helvetica", size=9)
    if legal_name and legal_name != display_name:
        pdf.set_x(MARGIN_MM)
        pdf.multi_cell(CONTENT_WIDTH_MM, 4.5, _latin1(legal_name))
        y = pdf.get_y()

    for part in address_parts:
        if part:
            pdf.set_x(MARGIN_MM)
            pdf.multi_cell(CONTENT_WIDTH_MM, 4.5, _latin1(part))
            y = pdf.get_y()

    if siret:
        pdf.set_x(MARGIN_MM)
        pdf.multi_cell(CONTENT_WIDTH_MM, 4.5, _latin1(f"SIRET : {siret}"))
        y = pdf.get_y()
    if vat:
        pdf.set_x(MARGIN_MM)
        pdf.multi_cell(CONTENT_WIDTH_MM, 4.5, _latin1(f"TVA : {vat}"))
        y = pdf.get_y()

    return y + 4


def _draw_title_block(pdf: FPDF, invoice: dict[str, Any], y: float) -> float:
    doc_type = invoice.get("document_type") or "Document"
    doc_number = invoice.get("document_number") or ""
    date = invoice.get("business_date") or invoice.get("issued_at") or ""

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(MARGIN_MM, y)
    pdf.multi_cell(CONTENT_WIDTH_MM, 8, _latin1(doc_type.upper()))
    y = pdf.get_y() + 1

    pdf.set_font("Helvetica", size=10)
    pdf.set_x(MARGIN_MM)
    pdf.multi_cell(CONTENT_WIDTH_MM, 5, _latin1(f"N° {doc_number}"))
    y = pdf.get_y()
    if date:
        pdf.set_x(MARGIN_MM)
        pdf.multi_cell(CONTENT_WIDTH_MM, 5, _latin1(f"Date : {date}"))
        y = pdf.get_y()

    return y + 4


def _draw_client_box(pdf: FPDF, invoice: dict[str, Any], y: float) -> float:
    customer = (invoice.get("customer_name") or "").strip()
    customer_vat = (invoice.get("customer_vat") or "").strip()
    if not customer and not customer_vat:
        return y

    box_height = 16 if customer_vat else 12
    pdf.set_draw_color(80, 80, 80)
    pdf.rect(MARGIN_MM, y, CONTENT_WIDTH_MM, box_height)

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(MARGIN_MM + 3, y + 3)
    pdf.cell(40, 5, _latin1("Client"))
    pdf.set_font("Helvetica", size=10)
    pdf.set_xy(MARGIN_MM + 3, y + 8)
    pdf.multi_cell(CONTENT_WIDTH_MM - 6, 4.5, _latin1(customer or "—"))
    if customer_vat:
        pdf.set_x(MARGIN_MM + 3)
        pdf.multi_cell(CONTENT_WIDTH_MM - 6, 4.5, _latin1(f"TVA client : {customer_vat}"))

    return y + box_height + 6


def _draw_line_items(pdf: FPDF, line_items: list[LineItem], y: float) -> float:
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(MARGIN_MM, y)
    pdf.cell(CONTENT_WIDTH_MM, 6, _latin1("Détail des prestations"))
    y = pdf.get_y() + 7

    col_designation = CONTENT_WIDTH_MM * 0.78
    col_qty = CONTENT_WIDTH_MM - col_designation

    pdf.set_font("Helvetica", "B", 9)
    pdf.set_xy(MARGIN_MM, y)
    pdf.cell(col_designation, 6, _latin1("Désignation"), border=1)
    pdf.cell(col_qty, 6, _latin1("Qté"), border=1, align="C")
    y += 6

    pdf.set_font("Helvetica", size=9)
    if not line_items:
        pdf.set_xy(MARGIN_MM, y)
        pdf.cell(col_designation, 6, _latin1("—"), border=1)
        pdf.cell(col_qty, 6, _latin1(""), border=1)
        return y + 8

    for item in line_items:
        if y > PAGE_HEIGHT_MM - MARGIN_MM - 20:
            pdf.add_page()
            y = MARGIN_MM
        row_height = _row_height(pdf, item.designation, col_designation - 4)
        pdf.set_xy(MARGIN_MM, y)
        pdf.multi_cell(col_designation, row_height, _latin1(item.designation), border=1)
        x_qty = MARGIN_MM + col_designation
        pdf.set_xy(x_qty, y)
        pdf.cell(col_qty, row_height, _latin1(item.quantity), border=1, align="C")
        y += row_height

    return y + 6


def _draw_vat_recap(pdf: FPDF, vat_lines: list[dict[str, Any]], y: float) -> float:
    if not vat_lines:
        return y

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(MARGIN_MM, y)
    pdf.cell(CONTENT_WIDTH_MM, 6, _latin1("Récapitulatif TVA"))
    y = pdf.get_y() + 7

    col_rate = 22
    col_ht = 40
    col_tva = 40
    col_ttc = CONTENT_WIDTH_MM - col_rate - col_ht - col_tva

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_xy(MARGIN_MM, y)
    pdf.cell(col_rate, 6, _latin1("Taux"), border=1, align="C")
    pdf.cell(col_ht, 6, _latin1("HT"), border=1, align="R")
    pdf.cell(col_tva, 6, _latin1("TVA"), border=1, align="R")
    pdf.cell(col_ttc, 6, _latin1("TTC"), border=1, align="R")
    y += 6

    pdf.set_font("Helvetica", size=8)
    for line in vat_lines:
        rate = str(line.get("rate", ""))
        ht = format_euros(line.get("ht_cents"))
        tva = format_euros(line.get("tva_cents"))
        ttc = format_euros(line.get("ttc_cents"))
        pdf.set_xy(MARGIN_MM, y)
        pdf.cell(col_rate, 6, _latin1(rate), border=1, align="C")
        pdf.cell(col_ht, 6, _latin1(ht), border=1, align="R")
        pdf.cell(col_tva, 6, _latin1(tva), border=1, align="R")
        pdf.cell(col_ttc, 6, _latin1(ttc), border=1, align="R")
        y += 6

    return y + 6


def _draw_totals(pdf: FPDF, invoice: dict[str, Any], y: float) -> float:
    label_width = 50
    value_width = CONTENT_WIDTH_MM - label_width

    pdf.set_font("Helvetica", "B", 10)
    rows = [
        ("Total HT", format_euros(invoice.get("amount_ht_cents"))),
        ("Total TVA", format_euros(invoice.get("amount_tva_cents"))),
        ("Total TTC", format_euros(invoice.get("amount_ttc_cents"))),
    ]
    for label, value in rows:
        pdf.set_xy(MARGIN_MM + CONTENT_WIDTH_MM - label_width - value_width, y)
        pdf.cell(label_width, 7, _latin1(label), border=0, align="R")
        pdf.cell(value_width, 7, _latin1(value), border=1, align="R")
        y += 7

    return y + 4


def _draw_payments(pdf: FPDF, payments: list[dict[str, Any]], y: float) -> float:
    if not payments:
        return y

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(MARGIN_MM, y)
    pdf.cell(CONTENT_WIDTH_MM, 6, _latin1("Paiements"))
    y = pdf.get_y() + 7

    col_mode = CONTENT_WIDTH_MM * 0.65
    col_amount = CONTENT_WIDTH_MM - col_mode

    pdf.set_font("Helvetica", size=9)
    for payment in payments:
        mode = payment.get("payment_mode") or payment.get("payment_method") or "—"
        amount = format_euros(payment.get("amount_cents"))
        pdf.set_xy(MARGIN_MM, y)
        pdf.cell(col_mode, 6, _latin1(mode), border=1)
        pdf.cell(col_amount, 6, _latin1(amount), border=1, align="R")
        y += 6

    return y + 4


def _draw_footer(pdf: FPDF, invoice: dict[str, Any]) -> None:
    ticket_id = invoice.get("nf525_ticket_id") or "—"
    doc_number = invoice.get("document_number") or "—"
    footer = (
        f"Reproduction d'archive fiscale NF525 — "
        f"Ticket {ticket_id} — Document {doc_number}"
    )
    pdf.set_y(PAGE_HEIGHT_MM - MARGIN_MM - 6)
    pdf.set_font("Helvetica", size=7)
    pdf.set_text_color(90, 90, 90)
    pdf.set_x(MARGIN_MM)
    pdf.multi_cell(CONTENT_WIDTH_MM, 4, _latin1(footer), align="C")


def _row_height(pdf: FPDF, text: str, width: float) -> float:
    lines = pdf.multi_cell(width, 4.5, _latin1(text), dry_run=True, output="LINES")
    return max(6.0, len(lines) * 4.5)


def _table_headers(table) -> list[str]:
    first_row = table.find("tr")
    if not first_row:
        return []
    return [_cell_text(cell) for cell in first_row.find_all(["th", "td"])]


def _table_to_kv(table) -> dict[str, str]:
    kv: dict[str, str] = {}
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) >= 2:
            key = _cell_text(cells[0])
            value = _cell_text(cells[1])
            if key and key != "Field":
                kv[key] = value
    return kv


def _cell_text(cell) -> str:
    return cell.get_text(" ", strip=True)


def _latin1(text: str) -> str:
    """Keep text inside the Helvetica Windows-1252 set, including the euro sign."""
    if not text:
        return ""
    text = text.replace("\u2014", " - ").replace("\u2013", "-")
    return text.encode("cp1252", errors="replace").decode("cp1252")
