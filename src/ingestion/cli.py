"""CLI for ingesting NF525 root archives."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import DEFAULT_DB_PATH
from src.db.connection import connect
from src.ingestion.names import parse_root_filename
from src.ingestion.pipeline import ingest_root_archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest NF525 root archives")
    parser.add_argument("archives", nargs="+", help="Path to ExportNF525_*.zip files")
    parser.add_argument(
        "--no-skip-covered",
        action="store_true",
        help="Parse daily archives even when covered by monthly/annee",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path",
    )
    args = parser.parse_args(argv)

    conn = connect(args.db)
    exit_code = 0

    for archive_path in args.archives:
        path = Path(archive_path)
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            exit_code = 1
            continue

        root_info = parse_root_filename(path)
        print(f"Ingesting {path.name} ({root_info.code})...", flush=True)

        def on_progress(current: int, total: int, name: str) -> None:
            print(f"  [{current}/{total}] {name}", flush=True)

        results = ingest_root_archive(
            conn,
            path,
            skip_covered=not args.no_skip_covered,
            progress_callback=on_progress,
        )

        for result in results:
            print(
                f"  {result['archive']}: {result['status']} "
                f"(+{result.get('inserted', 0)} ~{result.get('updated', 0)} "
                f"skip={result.get('skipped', 0)})"
            )

    conn.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
