"""NF525 HTML journal parser."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from bs4 import BeautifulSoup

from src.ingestion.names import parse_period_from_html
from src.parser.models import (
    HotelHeader,
    JournalParse,
    ParsedDocument,
    ParsedPayment,
    VatLine,
)
from src.parser.money import parse_cents

H2_SPLIT_PATTERN = re.compile(r"(?i)<h2[^>]*>")
H2_TAG_PATTERN = re.compile(r"(?i)<h2([^>]*)>(.*?)</h2>", re.DOTALL)

SUBSECTION_HEADINGS = frozenset({"TVA", "Détails", "Paiements", "Total", "Débiteur"})

SECTION_END_MARKERS = (
    "Duplicates",
    "Factures",
    "Grand Totals",
    "EventLogs",
    "TaxArchives",
)

MAX_FRAGMENT_BYTES = 500_000
MAX_SEARCH_TEXT = 4000


def parse_journal(html_bytes: bytes | str) -> JournalParse:
    """Parse a full NF525 HTML journal into documents."""
    if isinstance(html_bytes, bytes):
        text = html_bytes.decode("utf-8-sig", errors="replace")
    else:
        text = html_bytes

    result = JournalParse()
    period_start, period_end = parse_period_from_html(text)
    result.period_start = period_start
    result.period_end = period_end

    result.hotel_header = _parse_hotel_header(text)
    customer_index = _parse_factures_customer_index(text)
    tickets_slice = _extract_tickets_section(text)

    if tickets_slice is None:
        result.warnings.append("No Tickets section found")
        result.section_counts = _count_sections(text)
        return result

    documents = _parse_tickets_documents(tickets_slice, customer_index, result.warnings)
    result.documents = documents
    result.section_counts = _count_sections(text)
    return result


def _extract_tickets_section(text: str) -> str | None:
    start_match = re.search(
        r"<h1[^>]*>\s*Tickets\b.*?</h1>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not start_match:
        return None

    start = start_match.end()
    end_match = re.search(
        r"<h1[^>]*>\s*(?:Duplicates|Factures|Grand Totals|EventLogs|TaxArchives)\b",
        text[start:],
        flags=re.IGNORECASE,
    )
    end = start + end_match.start() if end_match else len(text)
    return text[start:end]


def _count_sections(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for marker in ("Tickets", "Duplicates", "Factures", "Grand Totals", "EventLogs", "TaxArchives"):
        pattern = re.compile(
            rf"<h1[^>]*>\s*{re.escape(marker)}\b",
            flags=re.IGNORECASE,
        )
        counts[marker] = len(pattern.findall(text))
    return counts


def _parse_hotel_header(text: str) -> HotelHeader:
    header = HotelHeader()
    for table_html in re.findall(r"<table[^>]*>.*?</table>", text[:20000], re.DOTALL | re.IGNORECASE):
        soup = BeautifulSoup(table_html, "html.parser")
        kv = _table_to_kv(soup)
        if "Nom d'hôtel" in kv or "Numéro de Siret" in kv:
            header.display_name = kv.get("Nom d'hôtel", header.display_name)
            header.legal_name = kv.get("Raison Sociale", header.legal_name)
            header.siret = kv.get("Numéro de Siret", header.siret)
            header.vat_number = kv.get("Numéro de TVA", header.vat_number)
            header.address = kv.get("Rue 1", header.address)
            header.zip_code = kv.get("CP", header.zip_code)
            header.city = kv.get("Ville", header.city)
            header.country = kv.get("Pays", header.country)
            break
    return header


def _parse_factures_customer_index(text: str) -> dict[str, dict[str, str]]:
    start_match = re.search(
        r"<h1[^>]*>\s*Factures\b.*?</h1>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not start_match:
        return {}

    start = start_match.end()
    end_match = re.search(
        r"<h1[^>]*>\s*(?:Grand Totals|EventLogs|TaxArchives)\b",
        text[start:],
        flags=re.IGNORECASE,
    )
    end = start + end_match.start() if end_match else len(text)
    slice_text = text[start:end]

    index: dict[str, dict[str, str]] = {}
    for table_html in re.findall(r"<table[^>]*>.*?</table>", slice_text, re.DOTALL | re.IGNORECASE):
        soup = BeautifulSoup(table_html, "html.parser")
        headers = _table_headers(soup)
        if "DocumentNumber" not in headers and "CustomerName" not in headers:
            continue
        doc_idx = headers.index("DocumentNumber") if "DocumentNumber" in headers else None
        name_idx = headers.index("CustomerName") if "CustomerName" in headers else None
        vat_idx = headers.index("CustomerVATNumber") if "CustomerVATNumber" in headers else None
        if doc_idx is None:
            continue
        for row in soup.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= doc_idx:
                continue
            doc_num = _cell_text(cells[doc_idx])
            if not doc_num:
                continue
            index[doc_num] = {
                "name": _cell_text(cells[name_idx]) if name_idx is not None and len(cells) > name_idx else "",
                "vat": _cell_text(cells[vat_idx]) if vat_idx is not None and len(cells) > vat_idx else "",
            }
    return index


def _parse_tickets_documents(
    tickets_slice: str,
    customer_index: dict[str, dict[str, str]],
    warnings: list[str],
) -> list[ParsedDocument]:
    matches = list(H2_TAG_PATTERN.finditer(tickets_slice))
    if not matches:
        return []

    documents: list[ParsedDocument] = []
    current_doc: ParsedDocument | None = None
    current_fragments: list[str] = []

    for index, match in enumerate(matches):
        attrs = match.group(1)
        heading_text = match.group(2).strip()
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(tickets_slice)
        body = tickets_slice[body_start:body_end]
        opening_tag = f"<h2{attrs}>{heading_text}</h2>"

        heading_clean = re.sub(r"\s+", " ", heading_text).strip()
        if heading_clean in SUBSECTION_HEADINGS:
            if current_doc is not None:
                current_fragments.append(f"{opening_tag}{body}")
            continue

        if current_doc is not None:
            current_doc.html_fragment = "".join(current_fragments)
            _parse_document_fragment(current_doc, current_doc.html_fragment)
            _finalize_document(current_doc, customer_index, warnings)
            documents.append(current_doc)

        doc_type, doc_number = _parse_document_heading(heading_clean)
        if not doc_number:
            warnings.append(f"Could not parse document number from heading: {heading_clean}")
            current_doc = None
            current_fragments = []
            continue

        current_doc = ParsedDocument(
            document_type=doc_type,
            document_number=doc_number,
        )
        current_fragments = [f"{opening_tag}{body}"]

    if current_doc is not None:
        current_doc.html_fragment = "".join(current_fragments)
        _parse_document_fragment(current_doc, current_doc.html_fragment)
        _finalize_document(current_doc, customer_index, warnings)
        documents.append(current_doc)

    return documents


def _parse_document_heading(heading: str) -> tuple[str, str]:
    tokens = heading.split()
    if not tokens:
        return "", ""
    if re.fullmatch(r"[0-9A-Za-z]+", tokens[-1]):
        return " ".join(tokens[:-1]), tokens[-1]
    return heading, ""


def _parse_document_fragment(doc: ParsedDocument, fragment: str) -> None:
    """Parse all tables from a document fragment with a single BeautifulSoup pass."""
    soup = BeautifulSoup(fragment, "html.parser")
    for table in soup.find_all("table"):
        headers = _table_headers(table)
        if not headers:
            continue
        if headers[:2] == ["Field", "Value"]:
            _apply_field_table(doc, table)
        elif "VatAmount" in headers:
            _parse_vat_table(doc, table, headers)
        elif "ProductLabel" in headers:
            _parse_details_table(doc, table, headers)
        elif "PaymentAmount" in headers:
            _parse_payments_table(doc, table, headers)
        elif "TotalAmountInclVat" in headers:
            _parse_total_table(doc, table, headers)
        elif "CustomerName" in headers and "NF525InvoiceID" in headers:
            _parse_debiteur_table(doc, table, headers)


def _apply_field_table(doc: ParsedDocument, table) -> None:
    kv = _table_to_kv(table)
    doc.nf525_ticket_id = kv.get("NF525TicketID", doc.nf525_ticket_id)
    doc.issued_at = _normalize_timestamp(kv.get("TimeStamp", doc.issued_at))
    hs_date = kv.get("HS_SystemDate", "")
    if hs_date:
        doc.business_date = hs_date[:10]
    elif doc.issued_at:
        doc.business_date = doc.issued_at[:10]
    doc.terminal_code = kv.get("TerminalCode", doc.terminal_code)
    doc.seller_name = kv.get("SellerName", doc.seller_name)
    doc.operator_name = kv.get("OperatorName", doc.operator_name)
    doc.operation_type = kv.get("OperationType", doc.operation_type)
    doc.ticket_status = kv.get("TicketStatus", doc.ticket_status)
    doc.signature = _collapse_whitespace(kv.get("Signature", doc.signature))
    if kv.get("DocumentNumber"):
        doc.document_number = kv.get("DocumentNumber", doc.document_number)
    if kv.get("PrintNumber"):
        try:
            doc.print_number = int(kv["PrintNumber"])
        except ValueError:
            pass
    if kv.get("NumberOfLines"):
        try:
            doc.number_of_lines = int(kv["NumberOfLines"])
        except ValueError:
            pass


def _parse_vat_table(doc: ParsedDocument, table, headers: list[str]) -> None:
    vat_lines: list[VatLine] = []
    tva_total = 0
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < len(headers):
            continue
        row_data = {headers[i]: _cell_text(cells[i]) for i in range(len(headers))}
        vat_cents = parse_cents(row_data.get("VatAmount"))
        if vat_cents is not None:
            tva_total += vat_cents
        vat_lines.append(
            VatLine(
                rate=row_data.get("VatRate", ""),
                ht_cents=parse_cents(row_data.get("TotalExclVat")),
                tva_cents=vat_cents,
                ttc_cents=parse_cents(row_data.get("TotalInclVat")),
            )
        )
    doc.amount_tva_cents = tva_total if vat_lines else doc.amount_tva_cents
    doc.vat_lines_json = json.dumps(
        [
            {
                "rate": line.rate,
                "ht_cents": line.ht_cents,
                "tva_cents": line.tva_cents,
                "ttc_cents": line.ttc_cents,
            }
            for line in vat_lines
        ]
    )


def _parse_details_table(doc: ParsedDocument, table, headers: list[str]) -> None:
    labels: list[str] = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["td", "th"])
        row_data = {
            headers[i]: _cell_text(cells[i])
            for i in range(min(len(headers), len(cells)))
        }
        label = row_data.get("ProductLabel", "")
        desc = row_data.get("Description", "")
        if label:
            labels.append(label)
        if desc:
            labels.append(desc)
    if labels:
        doc.search_text = " ".join(labels)[:MAX_SEARCH_TEXT]


def _parse_payments_table(doc: ParsedDocument, table, headers: list[str]) -> None:
    modes: set[str] = set()
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) < len(headers):
            continue
        row_data = {headers[i]: _cell_text(cells[i]) for i in range(len(headers))}
        mode = row_data.get("PaymentMode") or row_data.get("PaymentMethod", "")
        if mode:
            modes.add(mode)
        doc.payments.append(
            ParsedPayment(
                paid_at=_normalize_timestamp(row_data.get("TimeStamp", "")),
                payment_method=row_data.get("PaymentMethod", ""),
                payment_type=row_data.get("PaymentType", ""),
                payment_mode=row_data.get("PaymentMode", ""),
                account_number=row_data.get("AccountNumber", ""),
                amount_cents=parse_cents(row_data.get("PaymentAmount")),
                currency=row_data.get("CurrencyCode", "EUR") or "EUR",
            )
        )
    if modes:
        doc.payment_methods = " · ".join(sorted(modes))


def _parse_total_table(doc: ParsedDocument, table, headers: list[str]) -> None:
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["td", "th"])
        row_data = {
            headers[i]: _cell_text(cells[i])
            for i in range(min(len(headers), len(cells)))
        }
        ht = parse_cents(row_data.get("TotalAmountExclVat"))
        ttc = parse_cents(row_data.get("TotalAmountInclVat"))
        if ht is not None:
            doc.amount_ht_cents = ht
        if ttc is not None:
            doc.amount_ttc_cents = ttc


def _parse_debiteur_table(doc: ParsedDocument, table, headers: list[str]) -> None:
    for row in table.find_all("tr")[1:]:
        cells = row.find_all(["td", "th"])
        row_data = {
            headers[i]: _cell_text(cells[i])
            for i in range(min(len(headers), len(cells)))
        }
        name = row_data.get("CustomerName", "")
        if name and name.upper() != "N/A":
            doc.customer_name = name
        vat = row_data.get("CustomerVATNumber", "")
        if vat and vat.upper() != "N/A":
            doc.customer_vat = vat


def _finalize_document(
    doc: ParsedDocument,
    customer_index: dict[str, dict[str, str]],
    warnings: list[str],
) -> None:
    if not doc.customer_name and doc.document_number in customer_index:
        entry = customer_index[doc.document_number]
        doc.customer_name = entry.get("name", "")
        if not doc.customer_vat:
            doc.customer_vat = entry.get("vat", "")

    if doc.amount_tva_cents is None and doc.vat_lines_json != "[]":
        lines = json.loads(doc.vat_lines_json)
        doc.amount_tva_cents = sum(line.get("tva_cents") or 0 for line in lines)

    if doc.amount_ht_cents is None and doc.vat_lines_json != "[]":
        lines = json.loads(doc.vat_lines_json)
        doc.amount_ht_cents = sum(line.get("ht_cents") or 0 for line in lines)

    if doc.amount_ttc_cents is None and doc.amount_ht_cents is not None and doc.amount_tva_cents is not None:
        doc.amount_ttc_cents = doc.amount_ht_cents + doc.amount_tva_cents

    if (
        doc.amount_ht_cents is not None
        and doc.amount_tva_cents is not None
        and doc.amount_ttc_cents is not None
        and abs(doc.amount_ttc_cents - (doc.amount_ht_cents + doc.amount_tva_cents)) > 1
    ):
        warnings.append(
            f"Amount mismatch on {doc.document_type} {doc.document_number}"
        )

    fragment_bytes = doc.html_fragment.encode("utf-8")
    if len(fragment_bytes) > MAX_FRAGMENT_BYTES:
        doc.html_fragment = fragment_bytes[:MAX_FRAGMENT_BYTES].decode("utf-8", errors="ignore")
        warnings.append(
            f"HTML fragment truncated for {doc.document_type} {doc.document_number}"
        )

    doc.html_sha256 = hashlib.sha256(doc.html_fragment.encode("utf-8")).hexdigest()


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


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_timestamp(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
