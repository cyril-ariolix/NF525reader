"""Data models for parsed NF525 journal content."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HotelHeader:
    display_name: str = ""
    legal_name: str = ""
    siret: str = ""
    vat_number: str = ""
    address: str = ""
    zip_code: str = ""
    city: str = ""
    country: str = ""


@dataclass
class ParsedPayment:
    paid_at: str = ""
    payment_method: str = ""
    payment_type: str = ""
    payment_mode: str = ""
    account_number: str = ""
    amount_cents: int | None = None
    currency: str = "EUR"


@dataclass
class VatLine:
    rate: str = ""
    ht_cents: int | None = None
    tva_cents: int | None = None
    ttc_cents: int | None = None


@dataclass
class ParsedDocument:
    document_type: str
    document_number: str
    nf525_ticket_id: str = ""
    issued_at: str = ""
    business_date: str = ""
    amount_ht_cents: int | None = None
    amount_tva_cents: int | None = None
    amount_ttc_cents: int | None = None
    currency: str = "EUR"
    payment_methods: str = ""
    customer_name: str = ""
    customer_vat: str = ""
    seller_name: str = ""
    operator_name: str = ""
    terminal_code: str = ""
    operation_type: str = ""
    ticket_status: str = ""
    print_number: int | None = None
    number_of_lines: int | None = None
    signature: str = ""
    html_fragment: str = ""
    html_sha256: str = ""
    search_text: str = ""
    vat_lines_json: str = "[]"
    parse_warnings: str = ""
    payments: list[ParsedPayment] = field(default_factory=list)
    source_precedence: int = 1


@dataclass
class JournalParse:
    hotel_header: HotelHeader = field(default_factory=HotelHeader)
    documents: list[ParsedDocument] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    section_counts: dict[str, int] = field(default_factory=dict)
    period_start: str | None = None
    period_end: str | None = None
