"""Formatting helpers for the UI."""

from __future__ import annotations


def format_euros(cents: int | None) -> str:
    """Format integer cents as French euro display."""
    if cents is None:
        return "—"
    negative = cents < 0
    value = abs(cents)
    euros = value // 100
    remainder = value % 100
    formatted = f"{euros:,}".replace(",", " ") + f",{remainder:02d}"
    prefix = "-" if negative else ""
    return f"{prefix}{formatted} €"
