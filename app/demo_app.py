"""
Resolvix — Multilingual Support Ticket Assistant UI.
Phase 1 Working Prototype (In-Memory Semantic Search).
"""

from __future__ import annotations

import os
import sys
import time
import warnings
from pathlib import Path

# Keep the Streamlit terminal free of optional-deps / hub noise.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")

import numpy as np
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from embeddings.generate import generate_embedding, get_model

CSV_PATH = PROJECT_ROOT / "data" / "tickets_seed.csv"

st.set_page_config(
    page_title="Multilingual Support Ticket Assistant",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Clean, balanced typography without custom clutter
st.markdown(
    """
    <style>
    /* Hide sidebar and toggle */
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {
        display: none !important;
    }

    /* Keep container comfortably centered so screen does not feel stretched or empty */
    .block-container {
        max-width: 1200px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }

    /* Clean resolution box */
    .resolution-card {
        background-color: #f0fdf4;
        border-left: 4px solid #16a34a;
        padding: 12px 16px;
        border-radius: 4px;
        margin-top: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def load_embedding_model():
    """Load and cache the multilingual sentence-transformer singleton."""
    return get_model()


@st.cache_data
def load_seed_tickets_with_embeddings() -> list[dict]:
    """Load seed dataset from CSV and pre-compute embeddings in memory."""
    df = pd.read_csv(CSV_PATH)
    records = []
    for idx, row in df.iterrows():
        desc = str(row["description"])
        vec = generate_embedding(desc)
        records.append({
            "ticket_id": idx + 101,
            "description": desc,
            "language_code": str(row.get("language_code", "en")),
            "category_name": str(row.get("category_name", "General")),
            "resolution": str(row.get("resolution", "")),
            "priority": str(row.get("priority", "MEDIUM")),
            "embedding": vec,
        })
    return records


def find_similar_in_memory(
    query_vec: np.ndarray,
    tickets: list[dict],
    top_n: int = 3,
    category_filter: str = "All",
    priority_filter: str = "All",
) -> list[dict]:
    """Calculate cosine similarity against in-memory dataset with hybrid relational filtering."""
    results = []
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return []

    for t in tickets:
        # Relational SQL-equivalent predicates
        if category_filter != "All" and t["category_name"].lower() != category_filter.lower():
            continue
        if priority_filter != "All" and t["priority"].upper() != priority_filter.upper():
            continue

        t_vec = t["embedding"]
        t_norm = np.linalg.norm(t_vec)
        if t_norm == 0:
            continue
        sim = float(np.dot(query_vec, t_vec) / (query_norm * t_norm))
        dist = max(0.0, 1.0 - sim)
        results.append({
            "ticket_id": t["ticket_id"],
            "description": t["description"],
            "language_code": t["language_code"],
            "category_name": t["category_name"],
            "resolution": t["resolution"],
            "priority": t["priority"],
            "similarity_score": sim,
            "similarity_distance": dist,
        })

    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    return results[:top_n]


def main() -> None:
    st.title("Multilingual Support Ticket Assistant")
    st.caption(
        "Semantic similarity search powered by sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2, 384 dimensions). "
        "Finds previously resolved tickets matching a new query across English, Hindi, and Tamil."
    )

    with st.spinner("Loading multilingual embedding model..."):
        model = load_embedding_model()
        tickets = load_seed_tickets_with_embeddings()

    st.divider()

    # Session State for inputs
    if "selected_query" not in st.session_state:
        st.session_state["selected_query"] = ""

    # Two-column balanced layout (Input on Left, Results on Right)
    col_left, col_right = st.columns([1, 1.4], gap="large")

    with col_left:
        st.subheader("New Ticket Query")

        # Clean preset dropdown (no emojis)
        preset_choice = st.selectbox(
            "Load sample query:",
            options=[
                "— Custom input (type below) —",
                "Hindi: Password reset link expired (Login)",
                "English: Billed twice on monthly subscription (Billing)",
                "Tamil: Mobile app crash on splash screen (Technical)",
                "Hindi: UPI payment deducted but order failed (Billing)",
                "English: Two-factor authentication SMS not delivered (Login)",
                "Hindi: Plan upgrade refund request (Refund)",
            ],
        )

        preset_mapping = {
            "Hindi: Password reset link expired (Login)": "मेरा पासवर्ड रीसेट नहीं हो रहा है — ईमेल में मिला रीसेट लिंक तुरंत समाप्त हो जाता है या अमान्य टोकन त्रुटि दिखाता है।",
            "English: Billed twice on monthly subscription (Billing)": "I was charged twice for my monthly subscription on the same invoice and need the extra charge reversed.",
            "Tamil: Mobile app crash on splash screen (Technical)": "latest version-ல் mobile app splash screen-க்குப் பிறகு immediately crash ஆகிறது; tickets open செய்ய முடியவில்லை.",
            "Hindi: UPI payment deducted but order failed (Billing)": "यूपीआई से पैसे कट गए हैं लेकिन भुगतान असफल दिखा रहा है और ऑर्डर प्रोसेस नहीं हुआ।",
            "English: Two-factor authentication SMS not delivered (Login)": "Two-factor authentication code is not being delivered to my phone number via SMS.",
            "Hindi: Plan upgrade refund request (Refund)": "मैंने गलत प्लान चुन लिया था और अपग्रेड के 24 घंटे के अंदर रिफंड का अनुरोध कर रहा/रही हूँ।",
        }

        default_text = preset_mapping.get(preset_choice, "")
        if default_text:
            st.session_state["selected_query"] = default_text

        query_text = st.text_area(
            "Issue description:",
            value=st.session_state["selected_query"],
            height=130,
            placeholder="Enter support issue description in English, Hindi, or Tamil...",
        )

        lang_hint = st.selectbox(
            "Language hint:",
            options=["Auto-detect", "English", "Hindi", "Tamil"],
            help="Multilingual embedding model natively embeds all three languages into the same vector space.",
        )

        # Hybrid Search relational filter controls
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            category_filter = st.selectbox(
                "Filter Category:",
                options=["All", "Billing", "Technical", "Login", "Account", "Refund", "General"],
                help="Oracle 23ai Hybrid Search: Relational WHERE clause combined with vector distance.",
            )
        with f_col2:
            priority_filter = st.selectbox(
                "Filter Priority:",
                options=["All", "URGENT", "HIGH", "MEDIUM", "LOW"],
                help="Filter by ticket priority level.",
            )

        btn_col1, btn_col2 = st.columns([2, 1])
        with btn_col1:
            search_clicked = st.button("Find Similar Tickets", type="primary", use_container_width=True)
        with btn_col2:
            if st.button("Clear", use_container_width=True):
                st.session_state["selected_query"] = ""
                st.rerun()

    with col_right:
        st.subheader("Search Results")

        active_query = query_text.strip()

        if search_clicked or active_query:
            if not active_query:
                st.warning("Please enter a ticket description before searching.")
            else:
                start_time = time.time()
                with st.spinner("Embedding text and searching vector store..."):
                    query_vec = generate_embedding(active_query)
                    results = find_similar_in_memory(
                        query_vec,
                        tickets,
                        top_n=3,
                        category_filter=category_filter,
                        priority_filter=priority_filter,
                    )
                elapsed_ms = (time.time() - start_time) * 1000.0

                filter_info = []
                if category_filter != "All":
                    filter_info.append(f"Category: `{category_filter}`")
                if priority_filter != "All":
                    filter_info.append(f"Priority: `{priority_filter}`")
                filter_suffix = f"  |  Filter: {', '.join(filter_info)}" if filter_info else ""

                st.caption(f"Found {len(results)} matching tickets in {elapsed_ms:.1f} ms{filter_suffix}")

                if not results:
                    st.info(
                        f"No tickets found matching the relational filter (Category: `{category_filter}`, Priority: `{priority_filter}`). "
                        "Try changing filters to 'All'."
                    )
                else:
                    for rank, match in enumerate(results, start=1):
                        score = float(match.get("similarity_score") or 0.0)
                        percent = max(0.0, min(100.0, score * 100.0))
                        ticket_id = match.get("ticket_id")
                        lang = str(match.get("language_code", "en")).upper()
                        category = match.get("category_name", "General")
                        priority = match.get("priority", "MEDIUM")

                        if percent >= 80.0:
                            conf_badge = "High"
                        elif percent >= 65.0:
                            conf_badge = "Moderate"
                        else:
                            conf_badge = "Low"

                        with st.container(border=True):
                            st.markdown(
                                f"**#{rank} &middot; Ticket `{ticket_id}`** &nbsp;|&nbsp; "
                                f"Language: `{lang}` &nbsp;|&nbsp; "
                                f"Category: **{category}** &nbsp;|&nbsp; "
                                f"Priority: `{priority}` &nbsp;|&nbsp; "
                                f"Confidence: `{conf_badge}`"
                            )
                            st.progress(percent / 100.0)
                            st.caption(f"Similarity score: **{percent:.1f}%** (Cosine distance: {float(match.get('similarity_distance') or 0):.4f})")

                            st.markdown("**Original Description:**")
                            st.write(match.get("description") or "(empty)")

                            st.markdown("**Suggested Resolution:**")
                            resolution = match.get("resolution")
                            if resolution:
                                st.success(resolution)
                            else:
                                st.info("No resolution text stored for this ticket.")

                    # Oracle 23ai Hybrid Search SQL Simulation Expander
                    with st.expander("View Equivalent Oracle 23ai Hybrid Search SQL"):
                        where_parts = ["status IN ('RESOLVED', 'CLOSED')"]
                        if category_filter != "All":
                            where_parts.append(f"c.category_name = '{category_filter}'")
                        if priority_filter != "All":
                            where_parts.append(f"t.priority = '{priority_filter}'")
                        where_sql = "\n  AND ".join(where_parts)
                        st.code(
                            f"""-- Oracle Database 23ai Hybrid Vector + Relational Query
SELECT t.ticket_id, t.description, t.resolution, c.category_name, t.priority,
       VECTOR_DISTANCE(t.embedding, :query_vector, COSINE) AS distance
FROM tickets t
JOIN categories c ON t.category_id = c.category_id
WHERE {where_sql}
ORDER BY distance ASC
FETCH FIRST 3 ROWS ONLY;""",
                            language="sql",
                        )
        else:
            # Clean right-side guide
            with st.container(border=True):
                st.markdown("#### Ready to Search")
                st.write(
                    "Enter a new customer issue on the left or choose a sample query from the dropdown to run semantic similarity search."
                )


if __name__ == "__main__":
    main()

