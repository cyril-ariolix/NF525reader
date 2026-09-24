"""Tests for ingestion pipeline."""

import io
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pytest

from src.db.connection import connect
from src.ingestion.pipeline import ingest_root_archive

FIXTURES = Path(__file__).parent / "fixtures"


def _build_inner_zip(html_content: bytes, basename: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{basename}.html", html_content)
        zf.writestr(f"{basename}.rsa", b"\xef\xbb\xbfTEST_SIGNATURE")
    return buffer.getvalue()


def _build_root_zip(members: dict[str, bytes]) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as root:
        for name, data in members.items():
            root.writestr(f"ExportNF525/{name}", data)
    return Path(tmp.name)


@pytest.fixture
def db_conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = connect(db_path)
        yield conn
        conn.close()


def test_monthly_then_daily_dedup(db_conn):
    old_html = (FIXTURES / "daily_old.html").read_bytes()
    monthly_inner = _build_inner_zip(old_html, "NF525CashData_201905_Monthly")
    daily_inner = _build_inner_zip(old_html, "NF525CashData_20190508_0452")

    with tempfile.TemporaryDirectory() as tmpdir:
        root_path = Path(tmpdir) / "ExportNF525_TestHotel_FR009999.zip"
        with zipfile.ZipFile(root_path, "w", zipfile.ZIP_STORED) as root:
            root.writestr("ExportNF525/NF525CashData_201905_Monthly.zip", monthly_inner)
            root.writestr("ExportNF525/NF525CashData_20190508_0452.zip", daily_inner)

        results = ingest_root_archive(db_conn, root_path)
        completed = [r for r in results if r["status"] == "completed"]
        assert len(completed) >= 1
        count = db_conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        assert count == 3

        results2 = ingest_root_archive(db_conn, root_path)
        assert all(
            r["status"] in ("skipped_sha256", "skipped_covered") for r in results2
        )
        count2 = db_conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        assert count2 == count


def test_daily_then_monthly_updates_precedence(db_conn):
    old_html = (FIXTURES / "daily_old.html").read_bytes()
    monthly_inner = _build_inner_zip(old_html, "NF525CashData_201905_Monthly")
    daily_inner = _build_inner_zip(old_html, "NF525CashData_20190508_0452")

    with tempfile.TemporaryDirectory() as tmpdir:
        root_path = Path(tmpdir) / "ExportNF525_TestHotel_FR009998.zip"
        with zipfile.ZipFile(root_path, "w", zipfile.ZIP_STORED) as root:
            root.writestr("ExportNF525/NF525CashData_20190508_0452.zip", daily_inner)
            root.writestr("ExportNF525/NF525CashData_201905_Monthly.zip", monthly_inner)

        ingest_root_archive(db_conn, root_path, skip_covered=False)

        row = db_conn.execute(
            "SELECT source_precedence FROM invoices WHERE document_number = '09000001'"
        ).fetchone()
        assert row["source_precedence"] == 3


def test_hotel_identity_from_filename_not_siret(db_conn):
    old_html = (FIXTURES / "daily_old.html").read_bytes()
    inner = _build_inner_zip(old_html, "NF525CashData_20190508_0452")

    with tempfile.TemporaryDirectory() as tmpdir:
        root1 = Path(tmpdir) / "ExportNF525_HotelA_FR009991.zip"
        root2 = Path(tmpdir) / "ExportNF525_HotelB_FR009992.zip"
        for root_path in (root1, root2):
            with zipfile.ZipFile(root_path, "w", zipfile.ZIP_STORED) as root:
                root.writestr("ExportNF525/NF525CashData_20190508_0452.zip", inner)

        ingest_root_archive(db_conn, root1)
        ingest_root_archive(db_conn, root2)

    hotels = db_conn.execute("SELECT code FROM hotels ORDER BY code").fetchall()
    assert len(hotels) == 2


def test_broken_nested_member_does_not_abort(db_conn):
    old_html = (FIXTURES / "daily_old.html").read_bytes()
    good_inner = _build_inner_zip(old_html, "NF525CashData_201905_Monthly")
    bad_inner = b"not-a-valid-zip"

    with tempfile.TemporaryDirectory() as tmpdir:
        root_path = Path(tmpdir) / "ExportNF525_TestHotel_FR009993.zip"
        with zipfile.ZipFile(root_path, "w", zipfile.ZIP_STORED) as root:
            root.writestr("ExportNF525/NF525CashData_20190509_1200.zip", bad_inner)
            root.writestr("ExportNF525/NF525CashData_201905_Monthly.zip", good_inner)

        results = ingest_root_archive(db_conn, root_path)

    statuses = {r["archive"]: r["status"] for r in results}
    assert statuses["NF525CashData_20190509_1200.zip"] == "failed"
    assert statuses["NF525CashData_201905_Monthly.zip"] == "completed"
    assert db_conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 3

    errors = db_conn.execute(
        "SELECT COUNT(*) FROM ingestion_logs WHERE level = 'error'"
    ).fetchone()[0]
    assert errors >= 1


def test_no_skip_covered_parses_daily(db_conn):
    old_html = (FIXTURES / "daily_old.html").read_bytes()
    monthly_inner = _build_inner_zip(old_html, "NF525CashData_201905_Monthly")
    daily_inner = _build_inner_zip(old_html, "NF525CashData_20190508_0452")

    with tempfile.TemporaryDirectory() as tmpdir:
        root_path = Path(tmpdir) / "ExportNF525_TestHotel_FR009994.zip"
        with zipfile.ZipFile(root_path, "w", zipfile.ZIP_STORED) as root:
            root.writestr("ExportNF525/NF525CashData_201905_Monthly.zip", monthly_inner)
            root.writestr("ExportNF525/NF525CashData_20190508_0452.zip", daily_inner)

        ingest_root_archive(db_conn, root_path, skip_covered=False)

    archives = db_conn.execute(
        "SELECT archive_name, status FROM source_archives ORDER BY archive_name"
    ).fetchall()
    daily_status = next(
        r["status"] for r in archives if "0452" in r["archive_name"]
    )
    assert daily_status == "completed"
