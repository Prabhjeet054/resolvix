"""
Streamlit UI for the Multilingual Support Ticket Assistant.

Embeds a new ticket description and retrieves similar resolved/closed tickets
from Oracle AI Vector Search.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from db.connection import get_connection
from embeddings.generate import generate_embedding, get_model
from embeddings.similarity_search import find_similar_tickets

st.set_page_config(
    page_title="Multilingual Support Ticket Assistant",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def load_embedding_model():
    """Load the sentence-transformer once per process (slow cold start)."""
    return get_model()


def render_result_card(rank: int, match: dict) -> None:
    """Display one similar-ticket result with score, metadata, and resolution."""
    score = float(match.get("similarity_score") or 0.0)
    # COSINE distance is ~0..2; clamp display percent to [0, 100].
    percent = max(0.0, min(100.0, score * 100.0))
    language = match.get("language_code") or "?"
    category = match.get("category_name") or "?"
    ticket_id = match.get("ticket_id")

    with st.container(border=True):
        st.markdown(
            f"### #{rank} · Ticket `{ticket_id}` · "
            f"`{language}` · **{category}**"
        )
        st.progress(percent / 100.0)
        st.caption(f"Similarity score: **{percent:.1f}%** "
                   f"(distance={float(match.get('similarity_distance') or 0):.4f})")

        st.markdown("**Original description**")
        st.write(match.get("description") or "(empty)")

        st.markdown("**Suggested resolution**")
        resolution = match.get("resolution")
        if resolution:
            st.success(resolution)
        else:
            st.info("No resolution text stored for this ticket.")


def main() -> None:
    """Render the similarity search form."""
    st.title("Multilingual Support Ticket Assistant")
    st.markdown(
        "Enter a new support issue in English, Hindi, or Tamil. "
        "The multilingual embedding model finds similar **resolved/closed** tickets."
    )

    # Warm the model early so the first click is faster.
    try:
        load_embedding_model()
    except Exception as exc:
        st.warning(f"Embedding model not ready yet: {exc}")

    description = st.text_area(
        "New ticket description",
        height=160,
        placeholder="e.g. Unable to reset my password — the reset link expires immediately...",
    )
    language_hint = st.selectbox(
        "Language hint (optional)",
        options=["Auto-detect", "English", "Hindi", "Tamil"],
        help="Auto-detect is a UI label only — the multilingual model embeds any language.",
    )

    if st.button("Find Similar Tickets", type="primary"):
        if not description or not description.strip():
            st.warning("Please enter a ticket description before searching.")
            return

        st.caption(f"Language hint selected: {language_hint}")

        with st.spinner("Embedding your text and searching Oracle Vector Store..."):
            try:
                # Ensure cached model is loaded before encode.
                load_embedding_model()
                query_embedding = generate_embedding(description)
                results = find_similar_tickets(query_embedding, top_n=3)
            except Exception as exc:
                st.error(
                    "Search failed — Oracle may be down, or the embedding step errored.\n\n"
                    f"Details: {exc}"
                )
                return

        if not results:
            st.info(
                "No similar resolved/closed tickets found. "
                "Try different wording, or confirm tickets have been ingested with embeddings."
            )
            return

        st.subheader(f"Top {len(results)} similar tickets")
        for rank, match in enumerate(results, start=1):
            render_result_card(rank, match)


main()
