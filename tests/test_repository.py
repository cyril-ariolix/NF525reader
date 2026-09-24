"""Tests for database repository."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.db.connection import connect
from src.db.repository import (
    SearchFilters,
    build_search_query,
    sanitize_fts_query,
    search_invoices,
    upsert_hotel,
    upsert_invoice,
)
from src.parser.models import ParsedDocument, ParsedPayment


@pytest.fixture
def db_conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = connect(db_path)
        yield conn
        conn.close()


def _sample_doc(**overrides) -> ParsedDocument:
    defaults = {
        "document_type": "Facture",
        "document_number": "09000001",
        "nf525_ticket_id": "1001",
        "issued_at": "2019-05-08 11:08:08",
        "business_date": "2019-05-08",
        "amount_ht_cents": 9091,
        "amount_tva_cents": 909,
        "amount_ttc_cents": 10000,
        "customer_name": "ACME Corp",
        "seller_name": "EC",
        "operator_name": "EC",
        "payment_methods": "CB / VISA",
        "search_text": "HEBERGEMENT Chambre",
        "html_fragment": "<h2>Facture 09000001</h2><table></table>",
        "html_sha256": "abc123",
        "payments": [
            ParsedPayment(
                payment_method="Other",
                payment_mode="CB / VISA",
                amount_cents=10000,
            )
        ],
    }
    defaults.update(overrides)
    return ParsedDocument(**defaults)


def test_schema_has_wal_and_tables(db_conn):
    mode = db_conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"

    fk = db_conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1

    tables = {
        row[0]
        for row in db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "hotels" in tables
    assert "invoices" in tables
    assert "invoice_payments" in tables
    assert "source_archives" in tables
    assert "ingestion_logs" in tables
    assert "invoices_fts" in tables


def test_connection_uses_check_same_thread_false():
    source = Path("src/db/connection.py").read_text(encoding="utf-8")
    assert "check_same_thread=False" in source


def test_schema_fts_triggers_explicit_columns():
    schema = Path("src/db/schema.sql").read_text(encoding="utf-8")
    assert "..." not in schema
    assert "old.document_number" in schema
    assert "old.customer_name" in schema
    assert "old.seller_name" in schema
    assert "old.operator_name" in schema
    assert "old.payment_methods" in schema
    assert "old.search_text" in schema
    assert "new.document_number" in schema


def test_upsert_hotel_by_code(db_conn):
    id1 = upsert_hotel(
        db_conn,
        "FR005081",
        "HotelRenoirCannes",
        display_name="Hôtel Renoir",
        siret="48361787400043",
    )
    id2 = upsert_hotel(
        db_conn,
        "FR005082",
        "HotelCezanne",
        display_name="Cezanne Hotel",
        siret="48361787400043",
    )
    assert id1 != id2

    rows = db_conn.execute("SELECT code, siret FROM hotels ORDER BY code").fetchall()
    assert len(rows) == 2
    assert rows[0]["code"] == "FR005081"
    assert rows[1]["code"] == "FR005082"


def test_upsert_invoice_fts_lifecycle(db_conn):
    hotel_id = upsert_hotel(db_conn, "FR005081", "HotelRenoirCannes")
    db_conn.execute(
        """
        INSERT INTO source_archives (
          hotel_id, archive_name, root_filename, kind, precedence, sha256,
          status, ingested_at
        ) VALUES (?, 'test.zip', 'root.zip', 'daily', 1, 'sha', 'completed', 'now')
        """,
        (hotel_id,),
    )
    archive_id = db_conn.execute("SELECT id FROM source_archives").fetchone()[0]

    doc = _sample_doc()
    result = upsert_invoice(db_conn, hotel_id, archive_id, doc, 1, "2019-05-08")
    assert result == "inserted"
    db_conn.commit()

    fts = db_conn.execute(
        "SELECT * FROM invoices_fts WHERE customer_name MATCH 'ACME'"
    ).fetchall()
    assert len(fts) == 1

    doc2 = _sample_doc(customer_name="Updated Customer", html_sha256="def456")
    result = upsert_invoice(db_conn, hotel_id, archive_id, doc2, 3, "2019-05-31")
    assert result == "updated"
    db_conn.commit()

    fts = db_conn.execute(
        "SELECT * FROM invoices_fts WHERE customer_name MATCH 'Updated'"
    ).fetchall()
    assert len(fts) == 1

    invoice_id = db_conn.execute("SELECT id FROM invoices").fetchone()[0]
    db_conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    db_conn.commit()

    fts = db_conn.execute(
        "SELECT * FROM invoices_fts WHERE customer_name MATCH 'Updated'"
    ).fetchall()
    assert len(fts) == 0


def test_upsert_invoice_dedup_skips(db_conn):
    hotel_id = upsert_hotel(db_conn, "FR005081", "HotelRenoirCannes")
    db_conn.execute(
        """
        INSERT INTO source_archives (
          hotel_id, archive_name, root_filename, kind, precedence, sha256,
          status, ingested_at
        ) VALUES (?, 'monthly.zip', 'root.zip', 'monthly', 3, 'sha1', 'completed', 'now')
        """,
        (hotel_id,),
    )
    archive_id = db_conn.execute("SELECT id FROM source_archives").fetchone()[0]

    doc = _sample_doc()
    assert upsert_invoice(db_conn, hotel_id, archive_id, doc, 3, "2019-05-31") == "inserted"

    doc_daily = _sample_doc(html_sha256="different")
    assert (
        upsert_invoice(db_conn, hotel_id, archive_id, doc_daily, 1, "2019-05-08")
        == "skipped"
    )

    count = db_conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
    assert count == 1


def test_search_filters(db_conn):
    hotel_id = upsert_hotel(db_conn, "FR005081", "HotelRenoirCannes", display_name="Renoir")
    hotel_id2 = upsert_hotel(db_conn, "FR005082", "HotelCezanne", display_name="Cezanne")
    db_conn.execute(
        """
        INSERT INTO source_archives (
          hotel_id, archive_name, root_filename, kind, precedence, sha256,
          status, ingested_at
        ) VALUES (?, 'a.zip', 'root.zip', 'daily', 1, 'sha', 'completed', 'now')
        """,
        (hotel_id,),
    )
    archive_id = db_conn.execute("SELECT id FROM source_archives").fetchone()[0]

    upsert_invoice(
        db_conn,
        hotel_id,
        archive_id,
        _sample_doc(
            document_number="09000001",
            business_date="2019-05-08",
            amount_ttc_cents=10000,
            search_text="HEBERGEMENT",
        ),
        1,
        "2019-05-08",
    )
    upsert_invoice(
        db_conn,
        hotel_id,
        archive_id,
        _sample_doc(
            document_number="09000002",
            business_date="2019-06-15",
            amount_ttc_cents=25000,
            customer_name="WEEKENDESK",
            search_text="Cocktail",
            document_type="Facture",
        ),
        1,
        "2019-06-15",
    )
    upsert_invoice(
        db_conn,
        hotel_id2,
        archive_id,
        _sample_doc(document_number="09000003", business_date="2019-05-10"),
        1,
        "2019-05-10",
    )
    db_conn.commit()

    rows, total = search_invoices(
        db_conn, SearchFilters(hotel_id=hotel_id, document_types=["Facture"])
    )
    assert total == 2

    rows, total = search_invoices(
        db_conn,
        SearchFilters(
            hotel_id=hotel_id,
            date_from="2019-06-01",
            date_to="2019-06-30",
            document_types=["Facture"],
        ),
    )
    assert total == 1
    assert rows[0]["document_number"] == "09000002"

    rows, total = search_invoices(
        db_conn,
        SearchFilters(
            hotel_id=hotel_id,
            amount_min_cents=20000,
            amount_max_cents=30000,
            document_types=["Facture"],
        ),
    )
    assert total == 1

    rows, total = search_invoices(
        db_conn,
        SearchFilters(text_query="WEEKENDESK", document_types=["Facture"]),
    )
    assert total == 1

    rows, total = search_invoices(
        db_conn,
        SearchFilters(
            hotel_id=hotel_id,
            text_query='HEBERGEMENT "quoted"',
            document_types=["Facture"],
        ),
    )
    assert total == 1

    rows, total = search_invoices(
        db_conn, SearchFilters(document_types=["Facture"])
    )
    assert total == 3


def test_sanitize_fts_query():
    assert sanitize_fts_query('test "quoted"') == "test*"
    assert sanitize_fts_query("AND OR NOT") is None


def test_build_search_query_no_hotel():
    _, count_sql, params = build_search_query(
        SearchFilters(document_types=["Facture"])
    )
    assert "hotel_id" not in count_sql
    assert params == ["Facture"]
