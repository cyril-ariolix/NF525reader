"""Main Streamlit application page."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from src.config import DEFAULT_DB_PATH
from src.db.connection import connect
from src.db.repository import (
    distinct_payment_modes,
    get_invoice,
    list_hotels,
    search_invoices,
)
from src.ingestion.pipeline import ingest_root_archive
from src.ui.format import format_euros
from src.ui.inspector import render_inspector
from src.ui.search import build_filters_from_sidebar

PAGE_SIZE = 50


def get_connection():
    if "db_conn" not in st.session_state:
        st.session_state["db_conn"] = connect(DEFAULT_DB_PATH)
    return st.session_state["db_conn"]


def main() -> None:
    st.set_page_config(
        page_title="Factures présentes dans les archives",
        layout="wide",
    )
    st.title("Factures présentes dans les archives")
    st.caption("Cherchez une facture, cliquez sur sa ligne, puis téléchargez le PDF.")
    st.markdown(
        """
        <style>
        [data-testid="stDataFrame"] [data-testid="stElementToolbar"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    conn = get_connection()
    hotels = list_hotels(conn)

    _render_import_section(conn, expanded=len(hotels) == 0)

    payment_modes = distinct_payment_modes(conn)
    filters = build_filters_from_sidebar(hotels, payment_modes)
    filters.text_query = _render_database_search()
    _reset_page_if_filters_changed(filters)

    if "page" not in st.session_state:
        st.session_state["page"] = 0

    offset = st.session_state["page"] * PAGE_SIZE
    rows, total = search_invoices(conn, filters, limit=PAGE_SIZE, offset=offset)

    if filters.text_query:
        st.write(f"**{total}** résultat(s) dans l’ensemble des archives")
    else:
        st.write(f"**{total}** résultat(s)")

    if rows:
        _render_invoice_table(rows)

        col_prev, col_page, col_next = st.columns([1, 2, 1])
        with col_prev:
            if st.button("← Précédent") and st.session_state["page"] > 0:
                st.session_state["page"] -= 1
                st.rerun()
        with col_page:
            last_page = max((total - 1) // PAGE_SIZE, 0)
            st.write(f"Page {st.session_state['page'] + 1} / {last_page + 1}")
        with col_next:
            if st.button("Suivant →") and (offset + PAGE_SIZE) < total:
                st.session_state["page"] += 1
                st.rerun()
    else:
        st.info(
            "Aucune facture ne correspond. Élargissez les dates ou le montant."
        )

    invoice_id = st.session_state.get("invoice_id")
    if invoice_id:
        invoice = get_invoice(conn, invoice_id)
        if invoice:
            render_inspector(invoice)
        else:
            st.warning("Document introuvable.")


def _render_database_search() -> str | None:
    """Search the full invoice database, not the rows currently on screen."""
    with st.form("archive_search"):
        typed = st.text_input(
            "Rechercher dans toutes les archives",
            value=st.session_state.get("db_query", ""),
            placeholder="Client, numéro, prestation…",
        )
        submitted = st.form_submit_button("Rechercher")

    if submitted:
        st.session_state["db_query"] = typed.strip()
        st.session_state["page"] = 0

    query = (st.session_state.get("db_query") or "").strip()
    return query or None


def _reset_page_if_filters_changed(filters) -> None:
    signature = (
        filters.hotel_id,
        filters.date_from,
        filters.date_to,
        filters.amount_min_cents,
        filters.amount_max_cents,
        tuple(filters.document_types or []),
        tuple(filters.payment_modes or []),
        filters.text_query,
    )
    previous = st.session_state.get("search_signature")
    st.session_state["search_signature"] = signature
    if previous is not None and previous != signature:
        st.session_state["page"] = 0


def _render_invoice_table(rows) -> None:
    frame = pd.DataFrame(
        [
            {
                "Date": row["business_date"],
                "Hôtel": row["hotel_display_name"] or row["hotel_code"],
                "Type": row["document_type"],
                "Numéro": row["document_number"],
                "Client": row["customer_name"],
                "TTC": format_euros(row["amount_ttc_cents"]),
                "Paiement": row["payment_methods"],
            }
            for row in rows
        ]
    )
    table_key = f"results_table_{st.session_state.get('page', 0)}"
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        key=table_key,
    )
    selected = st.session_state.get(table_key, {}).get("selection", {}).get("rows", [])
    if selected:
        st.session_state["invoice_id"] = int(rows[selected[0]]["id"])


def _render_import_section(conn, *, expanded: bool) -> None:
    with st.sidebar.expander("Importer une sauvegarde", expanded=expanded):
        st.caption(
            "Glissez ici le fichier ExportNF525_….zip reçu de HotSoft, "
            "ou indiquez son emplacement sur cet ordinateur."
        )
        local_path = st.text_input("Chemin du fichier ZIP", value="", key="import_path")
        if st.button("Lancer l'import", key="import_path_btn") and local_path.strip():
            path = Path(local_path.strip())
            if path.exists():
                _run_ingest(conn, path)
            else:
                st.error("Fichier introuvable.")

        uploaded = st.file_uploader(
            "Fichier ZIP",
            type=["zip"],
            key="import_upload",
        )
        if uploaded is not None:
            token = (uploaded.name, uploaded.size)
            if st.session_state.get("imported_upload") != token:
                st.session_state["imported_upload"] = token
                original_name = Path(uploaded.name).name
                dest_dir = Path(tempfile.mkdtemp(prefix="nf525-import-"))
                dest = dest_dir / original_name
                dest.write_bytes(uploaded.getvalue())
                _run_ingest(conn, dest)


def _run_ingest(conn, path: Path) -> None:
    progress = st.sidebar.progress(0)
    status = st.sidebar.empty()

    def on_progress(current: int, total: int, name: str) -> None:
        progress.progress(current / total if total else 1.0)
        status.text(f"Import en cours… {current} sur {total}")

    try:
        results = ingest_root_archive(conn, path, progress_callback=on_progress)
    except ValueError as exc:
        status.empty()
        progress.empty()
        st.sidebar.error(
            "Ce fichier n'est pas une sauvegarde HotSoft. "
            "Le nom doit ressembler à ExportNF525_NomHotel_FR000000.zip. "
            f"({exc})"
        )
        return
    completed = sum(1 for r in results if r["status"] == "completed")
    status.empty()
    progress.empty()
    st.sidebar.success(
        f"Import terminé. {completed} archive(s) traitée(s). "
        "Vous pouvez chercher les factures."
    )
