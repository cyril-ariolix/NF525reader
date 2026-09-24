"""Build printable HTML documents from invoice fragments."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

PRINT_CSS = """
@page { size: A4; margin: 12mm; }
body { font: 12px/1.35 Arial, Helvetica, sans-serif; color: #000; background: #fff; margin: 0; padding: 16px; }
table { border-collapse: collapse; width: 100%; }
td, th { border: 1px solid #333; padding: 4px 6px; vertical-align: top; }
pre { white-space: pre-wrap; word-break: break-all; font-size: 9px; }
.no-wrap { white-space: nowrap; }
h2, h3, tr { break-inside: avoid; page-break-inside: avoid; }
@media print { .noprint { display: none !important; } }
"""


def sanitize_fragment(html_fragment: str) -> str:
    """Remove unsafe tags and attributes from an HTML fragment."""
    soup = BeautifulSoup(html_fragment, "html.parser")

    for tag_name in ("script", "iframe", "object", "embed", "link", "meta", "style"):
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for tag in soup.find_all(True):
        attrs = dict(tag.attrs)
        for attr in list(attrs.keys()):
            if attr.startswith("on"):
                del tag.attrs[attr]

    return str(soup)


def build_printable_html(
    *,
    title: str,
    html_fragment: str,
) -> str:
    """Wrap a sanitized fragment in a self-contained printable document."""
    safe_fragment = sanitize_fragment(html_fragment)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>{_escape_html(title)}</title>
<style>{PRINT_CSS}</style>
</head>
<body>
<button class="noprint" onclick="window.print()">Imprimer / Enregistrer en PDF</button>
{safe_fragment}
</body>
</html>"""


def download_filename(code: str, document_type: str, document_number: str) -> str:
    safe_type = re.sub(r"[^\w\s-]", "", document_type).strip().replace(" ", "_")
    return f"{code}_{safe_type}_{document_number}.html"


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
