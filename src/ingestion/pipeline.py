"""Ingestion pipeline for root NF525 archives."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Callable

from src.db.repository import (
    archive_already_done,
    finish_archive,
    is_archive_period_covered,
    log_ingestion,
    start_archive,
    upsert_hotel,
    upsert_invoice,
)
from src.ingestion.archive_reader import iter_root_members, read_nested_archive
from src.ingestion.names import (
    NestedArchiveInfo,
    parse_nested_member,
    parse_period_from_html,
    parse_root_filename,
)
from src.parser.html_archive import parse_journal


ProgressCallback = Callable[[int, int, str], None]


def ingest_root_archive(
    conn: sqlite3.Connection,
    root_path: Path,
    *,
    skip_covered: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    """Ingest one root ExportNF525 zip file."""
    root_path = Path(root_path)
    root_info = parse_root_filename(root_path)
    hotel_id = upsert_hotel(conn, root_info.code, root_info.slug)
    conn.commit()

    members = iter_root_members(root_path)
    work_items: list[tuple] = []
    for member in members:
        try:
            nested_info = parse_nested_member(member.info.filename)
        except ValueError as exc:
            log_ingestion(
                conn,
                hotel_id=hotel_id,
                source_archive_id=None,
                level="warning",
                event="invalid_member",
                message=str(exc),
            )
            continue
        work_items.append((member, nested_info))

    work_items.sort(
        key=lambda item: (
            -item[1].precedence,
            item[1].period_start or "",
        )
    )

    results: list[dict] = []
    total = len(work_items)

    for index, (member, nested_info) in enumerate(work_items, start=1):
        if progress_callback:
            progress_callback(index, total, nested_info.basename)

        if archive_already_done(conn, hotel_id, member.sha256):
            results.append(
                {
                    "archive": nested_info.basename,
                    "status": "skipped_sha256",
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 0,
                }
            )
            continue

        if (
            skip_covered
            and nested_info.kind == "daily"
            and is_archive_period_covered(
                conn, hotel_id, nested_info.period_start, nested_info.period_end
            )
        ):
            archive_id = start_archive(
                conn,
                hotel_id=hotel_id,
                archive_name=member.info.filename,
                root_filename=root_info.filename,
                kind=nested_info.kind,
                period_start=nested_info.period_start,
                period_end=nested_info.period_end,
                precedence=nested_info.precedence,
                sha256=member.sha256,
                rsa_signature=None,
                byte_size=member.info.file_size,
            )
            finish_archive(
                conn,
                archive_id,
                status="skipped_covered",
                document_count=0,
            )
            log_ingestion(
                conn,
                hotel_id=hotel_id,
                source_archive_id=archive_id,
                level="info",
                event="skipped_covered",
                message=f"Skipped covered daily archive {nested_info.basename}",
            )
            conn.commit()
            results.append(
                {
                    "archive": nested_info.basename,
                    "status": "skipped_covered",
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 0,
                }
            )
            continue

        try:
            result = _ingest_nested_member(
                conn,
                root_path,
                hotel_id,
                root_info.filename,
                member,
                nested_info,
            )
            results.append(result)
        except Exception as exc:
            conn.rollback()
            archive_id = start_archive(
                conn,
                hotel_id=hotel_id,
                archive_name=member.info.filename,
                root_filename=root_info.filename,
                kind=nested_info.kind,
                period_start=nested_info.period_start,
                period_end=nested_info.period_end,
                precedence=nested_info.precedence,
                sha256=member.sha256,
                rsa_signature=None,
                byte_size=member.info.file_size,
            )
            finish_archive(conn, archive_id, status="failed", error=str(exc))
            log_ingestion(
                conn,
                hotel_id=hotel_id,
                source_archive_id=archive_id,
                level="error",
                event="archive_failed",
                message=str(exc),
            )
            conn.commit()
            results.append(
                {
                    "archive": nested_info.basename,
                    "status": "failed",
                    "inserted": 0,
                    "updated": 0,
                    "skipped": 0,
                    "error": str(exc),
                }
            )

    return results


def _ingest_nested_member(
    conn: sqlite3.Connection,
    root_path: Path,
    hotel_id: int,
    root_filename: str,
    member,
    nested_info: NestedArchiveInfo,
) -> dict:
    content = read_nested_archive(root_path, member)
    journal = parse_journal(content.html_bytes)

    period_start = journal.period_start or nested_info.period_start
    period_end = journal.period_end or nested_info.period_end
    if nested_info.kind == "annee" and journal.period_start:
        period_start = journal.period_start
        period_end = journal.period_end

    root_meta = parse_root_filename(root_filename)
    header = journal.hotel_header

    conn.execute("BEGIN IMMEDIATE")
    inserted = updated = skipped = 0
    archive_id: int | None = None

    try:
        upsert_hotel(
            conn,
            root_meta.code,
            root_meta.slug,
            display_name=header.display_name,
            legal_name=header.legal_name,
            siret=header.siret,
            vat_number=header.vat_number,
            address=header.address,
            zip_code=header.zip_code,
            city=header.city,
            country=header.country,
        )

        archive_id = start_archive(
            conn,
            hotel_id=hotel_id,
            archive_name=member.info.filename,
            root_filename=root_filename,
            kind=nested_info.kind,
            period_start=period_start,
            period_end=period_end,
            precedence=nested_info.precedence,
            sha256=member.sha256,
            rsa_signature=content.rsa_signature,
            byte_size=content.byte_size,
        )

        for doc in journal.documents:
            doc.source_precedence = nested_info.precedence
            outcome = upsert_invoice(
                conn,
                hotel_id,
                archive_id,
                doc,
                nested_info.precedence,
                period_end,
            )
            if outcome == "inserted":
                inserted += 1
            elif outcome == "updated":
                updated += 1
            else:
                skipped += 1
                log_ingestion(
                    conn,
                    hotel_id=hotel_id,
                    source_archive_id=archive_id,
                    level="info",
                    event="skipped_duplicate_invoice",
                    message=f"Skipped duplicate {doc.document_type} {doc.document_number}",
                    document_number=doc.document_number,
                )

        for warning in journal.warnings:
            log_ingestion(
                conn,
                hotel_id=hotel_id,
                source_archive_id=archive_id,
                level="warning",
                event="parse_warning",
                message=warning,
            )

        finish_archive(
            conn,
            archive_id,
            status="completed",
            html_bytes=len(content.html_bytes),
            document_count=len(journal.documents),
            inserted_count=inserted,
            updated_count=updated,
            skipped_count=skipped,
            section_counts_json=json.dumps(journal.section_counts),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "archive": nested_info.basename,
        "status": "completed",
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }
