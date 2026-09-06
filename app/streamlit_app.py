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
)


@st.cache_resource
def load_embedding_model():
    """Load the sentence-transformer once per process (slow cold start)."""
    return get_model()


@st.cache_data(ttl=30)
def fetch_sidebar_stats() -> dict:
    """Pull lightweight ticket stats for the sidebar (cached ~30s)."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM tickets")
        total = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT ticket_status, COUNT(*) AS cnt
            FROM tickets
            GROUP BY ticket_status
            """
        )
        by_status = {str(status): int(cnt) for status, cnt in cursor.fetchall()}

        cursor.execute(
            """
            SELECT NVL(language_code, 'unknown') AS language_code, COUNT(*) AS cnt
            FROM tickets
            GROUP BY NVL(language_code, 'unknown')
            ORDER BY cnt DESC
            """
        )
        by_language = {
            str(language): int(cnt) for language, cnt in cursor.fetchall()
        }

        return {
            "total": total,
            "by_status": by_status,
            "by_language": by_language,
        }
    finally:
        cursor.close()
        conn.close()


def render_sidebar() -> None:
    """Show live DB stats; surface a clear error if Oracle is unreachable."""
    st.sidebar.header("Live ticket stats")
    try:
        stats = fetch_sidebar_stats()
    except Exception as exc:
        st.sidebar.error(
            "Cannot reach Oracle Database. "
            "Check Docker (`ticket-oracle-db`) and `.env` credentials.\n\n"
            f"Details: {exc}"
        )
        return

    st.sidebar.metric("Total tickets", stats["total"])

    st.sidebar.subheader("By status")
    for status in ("OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"):
        st.sidebar.write(f"{status}: **{stats['by_status'].get(status, 0)}**")

    st.sidebar.subheader("By language")
    for language, count in stats["by_language"].items():
        st.sidebar.write(f"{language}: **{count}**")

    st.sidebar.caption("Stats refresh at most every 30 seconds.")


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
    """Render sidebar stats and the similarity search form."""
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

    render_sidebar()

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
