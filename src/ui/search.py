"""Search filter helpers for Streamlit UI."""

from __future__ import annotations

import streamlit as st

from src.db.repository import SearchFilters
from src.parser.money import parse_cents


def build_filters_from_sidebar(
    hotels: list,
    payment_modes: list[str],
) -> SearchFilters:
    """Render sidebar filters and return a SearchFilters object."""
    st.sidebar.header("Recherche")

    hotel_options = {"Tous les hôtels": None}
    for hotel in hotels:
        label = hotel["display_name"] or hotel["code"]
        hotel_options[f"{label} ({hotel['code']})"] = hotel["id"]

    selected_hotel_label = st.sidebar.selectbox(
        "Hôtel",
        options=list(hotel_options.keys()),
    )
    hotel_id = hotel_options[selected_hotel_label]

    if (
        "selected_hotel_id" in st.session_state
        and st.session_state["selected_hotel_id"] != hotel_id
    ):
        st.session_state.pop("invoice_id", None)
    st.session_state["selected_hotel_id"] = hotel_id

    date_from_str = st.sidebar.text_input("Du", value="", placeholder="AAAA-MM-JJ")
    date_to_str = st.sidebar.text_input("Au", value="", placeholder="AAAA-MM-JJ")

    document_type = st.sidebar.selectbox(
        "Type de document",
        options=[
            "Facture",
            "Pro Forma",
            "Note",
            "Avoir",
            "DOCUMENT PROVISOIRE",
            "Tous les types",
        ],
        index=0,
    )
    document_types = None if document_type == "Tous les types" else [document_type]

    with st.sidebar.expander("Autres filtres"):
        amount_min = st.text_input("Montant min", value="", placeholder="€")
        amount_max = st.text_input("Montant max", value="", placeholder="€")
        payment_mode_selection = st.multiselect(
            "Mode de paiement",
            options=payment_modes,
        )

    return SearchFilters(
        hotel_id=hotel_id,
        date_from=date_from_str.strip() or None,
        date_to=date_to_str.strip() or None,
        amount_min_cents=parse_cents(amount_min) if amount_min.strip() else None,
        amount_max_cents=parse_cents(amount_max) if amount_max.strip() else None,
        document_types=document_types,
        payment_modes=payment_mode_selection or None,
        text_query=None,
    )
