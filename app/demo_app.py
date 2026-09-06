"""
Resolvix — Premium Multilingual Support Ticket Assistant UI.
Phase 1 Working PoC Prototype with Enhanced Aesthetics,
Quick Demo Scenarios, and Real-Time Vector Similarity.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from embeddings.generate import generate_embedding, get_model

CSV_PATH = PROJECT_ROOT / "data" / "tickets_seed.csv"

st.set_page_config(
    page_title="Resolvix — AI Multilingual Support Ticket Assistant",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Premium Custom CSS Injection
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    /* Hide default Streamlit sidebar and toggle permanently */
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {
        display: none !important;
    }

    /* Main container max width and padding */
    .block-container {
        max-width: 1160px;
        padding-top: 2rem;
        padding-bottom: 3.5rem;
    }

    /* Hero Header Styling */
    .hero-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(168, 85, 247, 0.12));
        color: #4f46e5;
        border: 1px solid rgba(99, 102, 241, 0.25);
        padding: 5px 14px;
        border-radius: 9999px;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        margin-bottom: 0.8rem;
    }

    .hero-title {
        font-size: 2.3rem;
        font-weight: 800;
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.4rem;
        letter-spacing: -0.02em;
    }

    .hero-subtitle {
        color: #64748b;
        font-size: 1.05rem;
        font-weight: 400;
        margin-bottom: 1.5rem;
        line-height: 1.5;
    }

    /* Stat Cards */
    .stat-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
        text-align: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .stat-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    }
    .stat-value {
        font-size: 1.45rem;
        font-weight: 800;
        color: #0f172a;
    }
    .stat-label {
        font-size: 0.75rem;
        color: #64748b;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 2px;
    }

    /* Result Card Enhancement */
    .result-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 16px;
        padding: 1.5rem;
        margin-bottom: 1.3rem;
        box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.05);
        transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .result-card:hover {
        border-color: #cbd5e1;
        box-shadow: 0 8px 30px -4px rgba(0, 0, 0, 0.09);
    }

    .badge-pill {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.3px;
        margin-right: 6px;
    }
    .badge-lang {
        background: #f1f5f9;
        color: #334155;
        border: 1px solid #cbd5e1;
    }
    .badge-cat {
        background: #ede9fe;
        color: #6d28d9;
        border: 1px solid #ddd6fe;
    }
    .badge-score {
        background: #dcfce7;
        color: #15803d;
        border: 1px solid #bbf7d0;
        font-weight: 800;
        font-size: 0.82rem;
    }

    .solution-box {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-left: 4px solid #16a34a;
        padding: 1rem 1.1rem;
        border-radius: 8px;
        margin-top: 0.9rem;
    }
    .solution-title {
        color: #15803d;
        font-weight: 700;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .solution-text {
        color: #166534;
        font-size: 0.95rem;
        line-height: 1.5;
        font-weight: 500;
    }

    /* Text area and button polish */
    .stTextArea textarea {
        border-radius: 12px !important;
        border: 1.5px solid #cbd5e1 !important;
        font-size: 0.95rem !important;
        transition: border-color 0.2s ease !important;
    }
    .stTextArea textarea:focus {
        border-color: #4f46e5 !important;
        box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15) !important;
    }
    .stButton button {
        border-radius: 10px !important;
        font-weight: 700 !important;
        padding: 0.6rem 1.8rem !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.3px !important;
        transition: all 0.2s ease !important;
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


def find_similar_in_memory(query_vec: np.ndarray, tickets: list[dict], top_n: int = 3) -> list[dict]:
    """Calculate cosine similarity against in-memory dataset and return top matches."""
    results = []
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return []

    for t in tickets:
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
    # Warm model & index seed dataset
    with st.spinner("Initializing multilingual vector engine..."):
        model = load_embedding_model()
        tickets = load_seed_tickets_with_embeddings()

    # Hero Header Section
    st.markdown(
        """
        <div class="hero-badge">⚡ Resolvix AI · Multilingual Resolution Engine</div>
        <div class="hero-title">Support Ticket Similarity Assistant</div>
        <div class="hero-subtitle">
            Instantly surface previously verified solutions using multilingual vector embeddings.
            Supports queries in <b>English, Hindi, and Tamil</b> with zero translation overhead.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Initialize Session State for Quick Demo Scenarios
    if "query_input" not in st.session_state:
        st.session_state["query_input"] = ""

    # Quick Demo Clickable Chips (Ideal for Live Reviews!)
    st.markdown("<p style='font-size: 0.85rem; font-weight: 700; color: #475569; margin-bottom: 6px;'>💡 QUICK DEMO SCENARIOS (CLICK TO TEST):</p>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        if st.button("🇮🇳 Hindi Login Issue", use_container_width=True):
            st.session_state["query_input"] = "मेरा पासवर्ड रीसेट नहीं हो रहा, लिंक एक्सपायर हो जाता है"
            st.rerun()

    with c2:
        if st.button("🇬🇧 English Double Billing", use_container_width=True):
            st.session_state["query_input"] = "I was charged twice for my monthly subscription on the same invoice"
            st.rerun()

    with c3:
        if st.button("🇮🇳 Tamil App Crash", use_container_width=True):
            st.session_state["query_input"] = "என் password-ஐ reset செய்ய முடியவில்லை, link expire ஆகிறது"
            st.rerun()

    with c4:
        if st.button("⚡ Urgent Plan Refund", use_container_width=True):
            st.session_state["query_input"] = "मैंने गलत प्लान चुन लिया था और 24 घंटे के अंदर रिफंड का अनुरोध कर रहा हूँ"
            st.rerun()

    # Search Input Box
    query_text = st.text_area(
        "Enter customer issue description:",
        value=st.session_state["query_input"],
        height=125,
        placeholder="Type customer issue in Hindi, Tamil, or English (e.g. मेरा पासवर्ड रीसेट नहीं हो रहा... / Unable to reset password...)",
    )

    btn_col, clear_col, _ = st.columns([1.8, 1, 4])
    with btn_col:
        search_pressed = st.button("🔍 Find Similar Tickets", type="primary", use_container_width=True)
    with clear_col:
        if st.button("Clear", use_container_width=True):
            st.session_state["query_input"] = ""
            st.rerun()

    # Search Execution
    active_query = query_text.strip()
    if search_pressed or (active_query and st.session_state["query_input"]):
        if not active_query:
            st.warning("Please enter or select a customer issue description above.")
            return

        start_time = time.time()
        with st.spinner("Generating 384-dimensional vector & performing semantic search..."):
            query_vector = generate_embedding(active_query)
            results = find_similar_in_memory(query_vector, tickets, top_n=3)
        latency_ms = (time.time() - start_time) * 1000.0

        st.markdown(f"<div style='margin-top: 1.5rem; margin-bottom: 0.8rem; font-size: 1.15rem; font-weight: 700; color: #1e293b;'>Top {len(results)} Semantically Relevant Matches <span style='font-size: 0.85rem; font-weight: 500; color: #64748b;'>({latency_ms:.1f}ms)</span></div>", unsafe_allow_html=True)

        for rank, match in enumerate(results, start=1):
            score = float(match.get("similarity_score") or 0.0)
            percent = max(0.0, min(100.0, score * 100.0))
            lang = match.get("language_code", "en").upper()
            cat = match.get("category_name", "General")
            t_id = match.get("ticket_id")
            priority = match.get("priority", "MEDIUM")
            desc = match.get("description", "")
            resolution = match.get("resolution", "")

            # Render polished HTML Card
            st.markdown(
                f"""
                <div class="result-card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.8rem;">
                        <div>
                            <span style="font-weight: 800; font-size: 1.05rem; color: #0f172a; margin-right: 8px;">#{rank} · Ticket #{t_id}</span>
                            <span class="badge-pill badge-lang">🌐 {lang}</span>
                            <span class="badge-pill badge-cat">📁 {cat}</span>
                            <span class="badge-pill" style="background:#fef3c7; color:#b45309; border:1px solid #fde68a;">⚡ {priority}</span>
                        </div>
                        <div>
                            <span class="badge-pill badge-score">✓ {percent:.1f}% Match</span>
                        </div>
                    </div>
                    <div style="color: #475569; font-size: 0.95rem; margin-bottom: 0.5rem; line-height: 1.5;">
                        <strong style="color: #1e293b;">Original Reported Issue:</strong> {desc}
                    </div>
                    <div class="solution-box">
                        <div class="solution-title">
                            <span>✅</span> Verified Suggested Resolution
                        </div>
                        <div class="solution-text">{resolution if resolution else 'No resolution recorded for this ticket.'}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
