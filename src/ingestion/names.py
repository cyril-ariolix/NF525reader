"""Filename parsing for NF525 archives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT_PATTERN = re.compile(
    r"^ExportNF525_(?P<slug>.+)_(?P<code>FR\d+)\.zip$",
    re.IGNORECASE,
)

NESTED_BASE = re.compile(r"^NF525CashData_(.+)\.zip$", re.IGNORECASE)

PRECEDENCE = {
    "annee": 4,
    "monthly": 3,
    "mois": 3,
    "range": 2,
    "daily": 1,
}


@dataclass(frozen=True)
class RootArchiveInfo:
    slug: str
    code: str
    filename: str


@dataclass(frozen=True)
class NestedArchiveInfo:
    archive_name: str
    basename: str
    kind: str
    precedence: int
    period_start: str | None
    period_end: str | None


def parse_root_filename(path: str | Path) -> RootArchiveInfo:
    """Extract hotel slug and FR code from a root archive filename."""
    name = Path(path).name
    match = ROOT_PATTERN.match(name)
    if not match:
        raise ValueError(f"Unrecognized root archive filename: {name}")
    return RootArchiveInfo(
        slug=match.group("slug"),
        code=match.group("code").upper(),
        filename=name,
    )


def parse_nested_member(member_name: str) -> NestedArchiveInfo:
    """Classify a nested NF525CashData zip member."""
    basename = Path(member_name).name
    match = NESTED_BASE.match(basename)
    if not match:
        raise ValueError(f"Unrecognized nested archive name: {basename}")

    token = match.group(1)

    if token.endswith("_Année"):
        kind = "annee"
        period_start, period_end = _parse_yyyymm_token(token.replace("_Année", ""))
    elif token.endswith("_Monthly"):
        kind = "monthly"
        period_start, period_end = _parse_yyyymm_token(token.replace("_Monthly", ""))
    elif token.endswith("_Mois"):
        kind = "mois"
        period_start, period_end = _parse_yyyymm_token(token.replace("_Mois", ""))
    else:
        parts = token.split("_")
        if len(parts) == 2 and len(parts[0]) == 8 and len(parts[1]) == 4:
            kind = "daily"
            start = _parse_date(parts[0])
            period_start = start.isoformat()
            period_end = start.isoformat()
        elif len(parts) == 2 and len(parts[0]) == 8 and len(parts[1]) == 8:
            start = _parse_date(parts[0])
            end = _parse_date(parts[1])
            span = (end - start).days
            if span <= 1:
                kind = "daily"
            else:
                kind = "range"
            period_start = start.isoformat()
            period_end = end.isoformat()
        else:
            raise ValueError(f"Cannot classify nested archive token: {token}")

    return NestedArchiveInfo(
        archive_name=member_name,
        basename=basename,
        kind=kind,
        precedence=PRECEDENCE[kind],
        period_start=period_start,
        period_end=period_end,
    )


def parse_period_from_html(text: str) -> tuple[str | None, str | None]:
    """Parse Jusqu'au date window from title or first h1."""
    patterns = [
        re.compile(
            r"Jusqu'au\s+(\d{4}-\d{2}-\d{2})(?:\s+\d{2}:\d{2}:\d{2})?",
            re.IGNORECASE,
        ),
        re.compile(
            r"Date d'Hôtel:\s*(\d{4}-\d{2}-\d{2}).*?Jusqu'au\s+(\d{4}-\d{2}-\d{2})",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"(\d{4}-\d{2}-\d{2})\s+\d{2}:\d{2}:\d{2}\s+Jusqu'au\s+(\d{4}-\d{2}-\d{2})",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(text[:8000])
        if match:
            groups = match.groups()
            if len(groups) == 1:
                return groups[0], groups[0]
            return groups[0], groups[1]

    return None, None


def is_safe_zip_member(member_name: str) -> bool:
    """Reject path traversal in zip member names."""
    path = Path(member_name)
    if path.is_absolute():
        return False
    return ".." not in path.parts


def _parse_date(token: str) -> date:
    return datetime.strptime(token, "%Y%m%d").date()


def _parse_yyyymm_token(token: str) -> tuple[str | None, str | None]:
    if len(token) != 6 or not token.isdigit():
        return None, None
    year = int(token[:4])
    month = int(token[4:6])
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start.isoformat(), end.isoformat()
