"""Database repository for NF525 archive data."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from src.parser.models import ParsedDocument, ParsedPayment

UpsertResult = Literal["inserted", "updated", "skipped"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SearchFilters:
    hotel_id: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    amount_min_cents: int | None = None
    amount_max_cents: int | None = None
    document_types: list[str] | None = None
    payment_modes: list[str] | None = None
    text_query: str | None = None


def upsert_hotel(
    conn: sqlite3.Connection,
    code: str,
    slug: str,
    *,
    display_name: str = "",
    legal_name: str = "",
    siret: str = "",
    vat_number: str = "",
    address: str = "",
    zip_code: str = "",
    city: str = "",
    country: str = "",
) -> int:
    """Insert or update a hotel by FR code."""
    now = utc_now()
    row = conn.execute("SELECT * FROM hotels WHERE code = ?", (code,)).fetchone()

    if row is None:
        cur = conn.execute(
            """
            INSERT INTO hotels (
              code, slug, display_name, legal_name, siret, vat_number,
              address, zip_code, city, country, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                slug,
                display_name or None,
                legal_name or None,
                siret or None,
                vat_number or None,
                address or None,
                zip_code or None,
                city or None,
                country or None,
                now,
                now,
            ),
        )
        return int(cur.lastrowid)

    updates: dict[str, Any] = {"updated_at": now}
    if display_name:
        updates["display_name"] = display_name
    if legal_name:
        updates["legal_name"] = legal_name
    if siret:
        updates["siret"] = siret
    if vat_number:
        updates["vat_number"] = vat_number
    if address:
        updates["address"] = address
    if zip_code:
        updates["zip_code"] = zip_code
    if city:
        updates["city"] = city
    if country:
        updates["country"] = country

    if len(updates) > 1:
        set_clause = ", ".join(f"{key} = ?" for key in updates)
        conn.execute(
            f"UPDATE hotels SET {set_clause} WHERE id = ?",
            (*updates.values(), row["id"]),
        )

    return int(row["id"])


def archive_already_done(conn: sqlite3.Connection, hotel_id: int, sha256: str) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM source_archives
        WHERE hotel_id = ? AND sha256 = ? AND status = 'completed'
        """,
        (hotel_id, sha256),
    ).fetchone()
    return row is not None


def start_archive(
    conn: sqlite3.Connection,
    *,
    hotel_id: int,
    archive_name: str,
    root_filename: str,
    kind: str,
    period_start: str | None,
    period_end: str | None,
    precedence: int,
    sha256: str,
    rsa_signature: str | None,
    byte_size: int | None,
) -> int:
    now = utc_now()
    existing = conn.execute(
        "SELECT id FROM source_archives WHERE hotel_id = ? AND archive_name = ?",
        (hotel_id, archive_name),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE source_archives SET
              root_filename = ?, kind = ?, period_start = ?, period_end = ?,
              precedence = ?, sha256 = ?, rsa_signature = ?, byte_size = ?,
              status = 'processing', error = NULL, ingested_at = ?
            WHERE id = ?
            """,
            (
                root_filename,
                kind,
                period_start,
                period_end,
                precedence,
                sha256,
                rsa_signature,
                byte_size,
                now,
                existing["id"],
            ),
        )
        return int(existing["id"])

    cur = conn.execute(
        """
        INSERT INTO source_archives (
          hotel_id, archive_name, root_filename, kind, period_start, period_end,
          precedence, sha256, rsa_signature, byte_size, status, ingested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'processing', ?)
        """,
        (
            hotel_id,
            archive_name,
            root_filename,
            kind,
            period_start,
            period_end,
            precedence,
            sha256,
            rsa_signature,
            byte_size,
            now,
        ),
    )
    return int(cur.lastrowid)


def finish_archive(
    conn: sqlite3.Connection,
    archive_id: int,
    *,
    status: str,
    html_bytes: int | None = None,
    document_count: int = 0,
    inserted_count: int = 0,
    updated_count: int = 0,
    skipped_count: int = 0,
    section_counts_json: str | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        UPDATE source_archives SET
          status = ?, html_bytes = ?, document_count = ?,
          inserted_count = ?, updated_count = ?, skipped_count = ?,
          section_counts_json = ?, error = ?
        WHERE id = ?
        """,
        (
            status,
            html_bytes,
            document_count,
            inserted_count,
            updated_count,
            skipped_count,
            section_counts_json,
            error,
            archive_id,
        ),
    )


def log_ingestion(
    conn: sqlite3.Connection,
    *,
    hotel_id: int | None,
    source_archive_id: int | None,
    level: str,
    event: str,
    message: str,
    document_number: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO ingestion_logs (
          hotel_id, source_archive_id, level, event, message, document_number, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (hotel_id, source_archive_id, level, event, message, document_number, utc_now()),
    )


def upsert_invoice(
    conn: sqlite3.Connection,
    hotel_id: int,
    source_archive_id: int,
    doc: ParsedDocument,
    incoming_precedence: int,
    incoming_period_end: str | None,
) -> UpsertResult:
    """Upsert an invoice with precedence-based deduplication."""
    existing = conn.execute(
        """
        SELECT id, source_precedence, html_sha256
        FROM invoices
        WHERE hotel_id = ? AND document_type = ? AND document_number = ?
        """,
        (hotel_id, doc.document_type, doc.document_number),
    ).fetchone()

    if existing is None:
        invoice_id = _insert_invoice(
            conn, hotel_id, source_archive_id, doc, incoming_precedence
        )
        _replace_payments(conn, invoice_id, doc.payments)
        return "inserted"

    should_update = False
    if incoming_precedence > existing["source_precedence"]:
        should_update = True
    elif (
        incoming_precedence == existing["source_precedence"]
        and doc.html_sha256 != existing["html_sha256"]
        and incoming_period_end is not None
    ):
        should_update = True

    if not should_update:
        return "skipped"

    invoice_id = int(existing["id"])
    now = utc_now()
    conn.execute(
        """
        UPDATE invoices SET
          source_archive_id = ?, source_precedence = ?, nf525_ticket_id = ?,
          issued_at = ?, business_date = ?, amount_ht_cents = ?, amount_tva_cents = ?,
          amount_ttc_cents = ?, currency = ?, payment_methods = ?, customer_name = ?,
          customer_vat = ?, seller_name = ?, operator_name = ?, terminal_code = ?,
          operation_type = ?, ticket_status = ?, print_number = ?, number_of_lines = ?,
          signature = ?, html_fragment = ?, html_sha256 = ?, search_text = ?,
          vat_lines_json = ?, parse_warnings = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            source_archive_id,
            incoming_precedence,
            doc.nf525_ticket_id,
            doc.issued_at,
            doc.business_date,
            doc.amount_ht_cents,
            doc.amount_tva_cents,
            doc.amount_ttc_cents,
            doc.currency,
            doc.payment_methods,
            doc.customer_name,
            doc.customer_vat,
            doc.seller_name,
            doc.operator_name,
            doc.terminal_code,
            doc.operation_type,
            doc.ticket_status,
            doc.print_number,
            doc.number_of_lines,
            doc.signature,
            doc.html_fragment,
            doc.html_sha256,
            doc.search_text,
            doc.vat_lines_json,
            doc.parse_warnings,
            now,
            invoice_id,
        ),
    )
    _replace_payments(conn, invoice_id, doc.payments)
    return "updated"


def _insert_invoice(
    conn: sqlite3.Connection,
    hotel_id: int,
    source_archive_id: int,
    doc: ParsedDocument,
    precedence: int,
) -> int:
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO invoices (
          hotel_id, source_archive_id, source_precedence, nf525_ticket_id,
          document_type, document_number, issued_at, business_date,
          amount_ht_cents, amount_tva_cents, amount_ttc_cents, currency,
          payment_methods, customer_name, customer_vat, seller_name, operator_name,
          terminal_code, operation_type, ticket_status, print_number, number_of_lines,
          signature, html_fragment, html_sha256, search_text, vat_lines_json,
          parse_warnings, created_at, updated_at
        ) VALUES (
          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            hotel_id,
            source_archive_id,
            precedence,
            doc.nf525_ticket_id,
            doc.document_type,
            doc.document_number,
            doc.issued_at,
            doc.business_date,
            doc.amount_ht_cents,
            doc.amount_tva_cents,
            doc.amount_ttc_cents,
            doc.currency,
            doc.payment_methods,
            doc.customer_name,
            doc.customer_vat,
            doc.seller_name,
            doc.operator_name,
            doc.terminal_code,
            doc.operation_type,
            doc.ticket_status,
            doc.print_number,
            doc.number_of_lines,
            doc.signature,
            doc.html_fragment,
            doc.html_sha256,
            doc.search_text,
            doc.vat_lines_json,
            doc.parse_warnings,
            now,
            now,
        ),
    )
    return int(cur.lastrowid)


def _replace_payments(
    conn: sqlite3.Connection,
    invoice_id: int,
    payments: list[ParsedPayment],
) -> None:
    conn.execute("DELETE FROM invoice_payments WHERE invoice_id = ?", (invoice_id,))
    for payment in payments:
        conn.execute(
            """
            INSERT INTO invoice_payments (
              invoice_id, paid_at, payment_method, payment_type, payment_mode,
              account_number, amount_cents, currency
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                payment.paid_at or None,
                payment.payment_method,
                payment.payment_type,
                payment.payment_mode,
                payment.account_number,
                payment.amount_cents,
                payment.currency,
            ),
        )


def sanitize_fts_query(text: str) -> str | None:
    """Build a safe FTS5 prefix query from user input."""
    cleaned = re.sub(r'"[^"]*"', " ", text)
    cleaned = re.sub(r'["*:()]+', " ", cleaned)
    for word in ("AND", "OR", "NOT"):
        cleaned = re.sub(rf"\b{word}\b", " ", cleaned, flags=re.IGNORECASE)
    tokens = [t for t in cleaned.split() if t]
    if not tokens:
        return None
    return " ".join(f"{token}*" for token in tokens)


def build_search_query(filters: SearchFilters) -> tuple[str, list[Any]]:
    """Build parameterized SQL for invoice search."""
    joins: list[str] = []
    where: list[str] = []
    params: list[Any] = []

    if filters.text_query:
        fts = sanitize_fts_query(filters.text_query)
        if fts:
            joins.append(
                "JOIN invoices_fts ON invoices_fts.rowid = invoices.id"
            )
            where.append("invoices_fts MATCH ?")
            params.append(fts)

    if filters.hotel_id is not None:
        where.append("invoices.hotel_id = ?")
        params.append(filters.hotel_id)

    if filters.date_from:
        where.append("invoices.business_date >= ?")
        params.append(filters.date_from)

    if filters.date_to:
        where.append("invoices.business_date <= ?")
        params.append(filters.date_to)

    if filters.amount_min_cents is not None:
        where.append("invoices.amount_ttc_cents >= ?")
        params.append(filters.amount_min_cents)

    if filters.amount_max_cents is not None:
        where.append("invoices.amount_ttc_cents <= ?")
        params.append(filters.amount_max_cents)

    if filters.document_types:
        placeholders = ", ".join("?" for _ in filters.document_types)
        where.append(f"invoices.document_type IN ({placeholders})")
        params.extend(filters.document_types)

    if filters.payment_modes:
        placeholders = ", ".join("?" for _ in filters.payment_modes)
        where.append(
            f"""EXISTS (
              SELECT 1 FROM invoice_payments p
              WHERE p.invoice_id = invoices.id AND p.payment_mode IN ({placeholders})
            )"""
        )
        params.extend(filters.payment_modes)

    join_sql = " ".join(joins)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    base = f"""
        SELECT invoices.*, hotels.code AS hotel_code, hotels.display_name AS hotel_display_name
        FROM invoices
        JOIN hotels ON hotels.id = invoices.hotel_id
        {join_sql}
        {where_sql}
    """

    count_sql = f"""
        SELECT COUNT(*)
        FROM invoices
        {join_sql}
        {where_sql}
    """

    return base, count_sql, params


def search_invoices(
    conn: sqlite3.Connection,
    filters: SearchFilters,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[sqlite3.Row], int]:
    """Search invoices with filters and pagination."""
    base, count_sql, params = build_search_query(filters)

    total = conn.execute(count_sql, params).fetchone()[0]

    query = (
        base
        + " ORDER BY invoices.business_date DESC, invoices.issued_at DESC, invoices.id DESC"
        + " LIMIT ? OFFSET ?"
    )
    rows = conn.execute(query, (*params, limit, offset)).fetchall()
    return rows, int(total)


def distinct_payment_modes(
    conn: sqlite3.Connection,
    hotel_id: int | None = None,
) -> list[str]:
    if hotel_id is None:
        rows = conn.execute(
            """
            SELECT DISTINCT payment_mode FROM invoice_payments
            WHERE payment_mode != ''
            ORDER BY payment_mode
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT DISTINCT p.payment_mode
            FROM invoice_payments p
            JOIN invoices i ON i.id = p.invoice_id
            WHERE i.hotel_id = ? AND p.payment_mode != ''
            ORDER BY p.payment_mode
            """,
            (hotel_id,),
        ).fetchall()
    return [row[0] for row in rows]


def list_hotels(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM hotels ORDER BY display_name, code"
    ).fetchall()


def get_invoice(conn: sqlite3.Connection, invoice_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT invoices.*, hotels.code AS hotel_code, hotels.display_name AS hotel_display_name
        FROM invoices
        JOIN hotels ON hotels.id = invoices.hotel_id
        WHERE invoices.id = ?
        """,
        (invoice_id,),
    ).fetchone()
    if row is None:
        return None

    payments = conn.execute(
        "SELECT * FROM invoice_payments WHERE invoice_id = ? ORDER BY id",
        (invoice_id,),
    ).fetchall()

    result = dict(row)
    result["payments"] = [dict(p) for p in payments]
    return result


def get_completed_covering_archives(
    conn: sqlite3.Connection,
    hotel_id: int,
) -> list[sqlite3.Row]:
    """Return completed monthly/mois/annee archives for covered-daily skip."""
    return conn.execute(
        """
        SELECT * FROM source_archives
        WHERE hotel_id = ? AND status = 'completed'
          AND kind IN ('monthly', 'mois', 'annee')
        """,
        (hotel_id,),
    ).fetchall()


def is_date_covered(
    conn: sqlite3.Connection,
    hotel_id: int,
    business_date: str,
) -> bool:
    """Check if a date falls within a completed monthly/mois/annee archive."""
    row = conn.execute(
        """
        SELECT 1 FROM source_archives
        WHERE hotel_id = ? AND status = 'completed'
          AND kind IN ('monthly', 'mois', 'annee')
          AND period_start <= ? AND period_end >= ?
        LIMIT 1
        """,
        (hotel_id, business_date, business_date),
    ).fetchone()
    return row is not None


def is_archive_period_covered(
    conn: sqlite3.Connection,
    hotel_id: int,
    period_start: str | None,
    period_end: str | None,
) -> bool:
    """Check if a daily archive's period is covered by a completed rollup."""
    if not period_start:
        return False
    end = period_end or period_start
    row = conn.execute(
        """
        SELECT 1 FROM source_archives
        WHERE hotel_id = ? AND status = 'completed'
          AND kind IN ('monthly', 'mois', 'annee')
          AND period_start <= ? AND period_end >= ?
        LIMIT 1
        """,
        (hotel_id, period_start, end),
    ).fetchone()
    return row is not None
