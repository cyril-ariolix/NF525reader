"""SQLite connection management."""

import sqlite3
from pathlib import Path

from src.config import DEFAULT_DB_PATH

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and thread-safe access."""
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-64000")

    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='hotels'"
    ).fetchone()
    if row is None:
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema_sql)
