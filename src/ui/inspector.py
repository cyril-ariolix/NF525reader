"""Invoice inspector with print preview."""

from __future__ import annotations

import streamlit as st

from src.ui.format import format_euros
from src.ui.invoice_pdf import build_invoice_pdf, pdf_filename
from src.ui.print_html import build_printable_html


def render_inspector(invoice: dict) -> None:
    """Render invoice metadata, PDF download, and optional HTML preview."""
    st.subheader(
        f"{invoice.get('document_type')} {invoice.get('document_number')}"
    )
    st.write(
        f"{invoice.get('business_date') or '—'} — "
        f"{invoice.get('customer_name') or '—'} — "
        f"{invoice.get('payment_methods') or '—'}"
    )

    pdf_bytes = build_invoice_pdf(invoice)
    st.download_button(
        label="Télécharger la facture (PDF)",
        data=pdf_bytes,
        file_name=pdf_filename(
            invoice.get("hotel_code", "hotel"),
            invoice.get("document_type", "doc"),
            invoice.get("document_number", "0"),
        ),
        mime="application/pdf",
        type="primary",
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("HT", format_euros(invoice.get("amount_ht_cents")))
    col2.metric("TVA", format_euros(invoice.get("amount_tva_cents")))
    col3.metric("TTC", format_euros(invoice.get("amount_ttc_cents")))

    title = (
        f"{invoice.get('hotel_display_name') or invoice.get('hotel_code')} — "
        f"{invoice.get('document_type')} {invoice.get('document_number')}"
    )
    printable = build_printable_html(
        title=title,
        html_fragment=invoice.get("html_fragment", ""),
    )

    with st.expander("Voir l'archive originale", expanded=False):
        st.iframe(printable, height=720)
