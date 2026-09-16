"""
Resolvix — Multilingual Support Ticket Assistant UI.
Phase 1 Working Prototype (In-Memory Semantic Search across 50+ Languages).
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

import embeddings.compat  # noqa: F401 (Applies Windows Smart App Control shims)
from embeddings.generate import generate_embedding, get_model
from embeddings.languages import (
    SUPPORTED_LANGUAGES,
    detect_language,
    get_language_display,
    get_language_flag,
    get_language_name,
)

CSV_PATH = PROJECT_ROOT / "data" / "tickets_seed.csv"

st.set_page_config(
    page_title="Multilingual Support Ticket Assistant (50+ Languages)",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Clean, balanced styling
st.markdown(
    """
    <style>
    /* Hide sidebar and toggle */
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {
        display: none !important;
    }

    /* Keep container comfortably centered */
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
            "language_code": str(row.get("language_code", "en")).lower(),
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
    language_filter: str = "All",
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
        if language_filter != "All" and t["language_code"].lower() != language_filter.lower():
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
        "Supports **50+ languages** natively in a shared multilingual vector space with zero-shot cross-lingual retrieval."
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

        # Multilingual presets covering diverse language families
        preset_mapping = {
            "— Custom input (type below) —": "",
            "Spanish 🇪🇸: Doble cobro en suscripción mensual (Billing)": "Se me cobró dos veces por la suscripción mensual en la misma factura y necesito el reembolso del cargo extra.",
            "French 🇫🇷: Impossible de réinitialiser le mot de passe (Login)": "Impossible de réinitialiser mon mot de passe — le lien de réinitialisation expire immédiatement ou renvoie une erreur de jeton invalide.",
            "German 🇩🇪: Die mobile App stürzt sofort ab (Technical)": "Die mobile App stürzt unmittelbar nach dem Startbildschirm ab und ich kann keine Tickets aufrufen.",
            "Japanese 🇯🇵: パスワード再設定リンク切れ (Login)": "パスワードを再設定できません。メール内のリセットリンクがすぐに期限切れになるか、無効なトークンエラーが発生します。",
            "Arabic 🇸🇦: خصم الاشتراك مرتين (Billing)": "تم خصم رسوم الاشتراك الشهري مرتين في نفس الفاتورة وأطلب استرداد المبلغ الإضافي.",
            "Hindi 🇮🇳: पासवर्ड रीसेट लिंक समाप्त (Login)": "मेरा पासवर्ड रीसेट नहीं हो रहा है — ईमेल में मिला रीसेट लिंक तुरंत समाप्त हो जाता है या अमान्य टोकन त्रुटि दिखाता है।",
            "Tamil 🇮🇳: மொபைல் ஆப் செயலிழப்பு (Technical)": "latest version-ல் mobile app splash screen-க்குப் பிறகு immediately crash ஆகிறது; tickets open செய்ய முடியவில்லை.",
            "Russian 🇷🇺: Не могу сбросить пароль (Login)": "Не могу сбросить пароль — ссылка для сброса в письме мгновенно истекает или выдает ошибку недействительного токена.",
            "English 🇬🇧: Billed twice on monthly subscription (Billing)": "I was charged twice for my monthly subscription on the same invoice and need the extra charge reversed.",
            "English 🇬🇧: Two-factor authentication SMS not delivered (Login)": "Two-factor authentication code is not being delivered to my phone number via SMS.",
        }

        preset_choice = st.selectbox(
            "Load sample query:",
            options=list(preset_mapping.keys()),
        )

        default_text = preset_mapping.get(preset_choice, "")
        if default_text:
            st.session_state["selected_query"] = default_text

        query_text = st.text_area(
            "Issue description:",
            value=st.session_state["selected_query"],
            height=130,
            placeholder="Enter support issue description in ANY of the 50+ supported languages...",
        )

        # Real-time language detection badge
        detected_lang_code = detect_language(query_text) if query_text.strip() else "en"
        detected_display = get_language_display(detected_lang_code)

        col_detect, col_hint = st.columns([1, 1])
        with col_detect:
            st.markdown(f"**Detected Language:** `{detected_display}`")
        with col_hint:
            lang_options = ["Auto-detect"] + [
                f"{info['flag']} {info['name']} ({code})"
                for code, info in sorted(SUPPORTED_LANGUAGES.items(), key=lambda x: x[1]["name"])
            ]
            manual_hint = st.selectbox(
                "Manual override:",
                options=lang_options,
                index=0,
                help="50+ languages natively embedded in the same 384-dimensional vector space.",
            )

        # Extract selected override language code if specified
        active_lang_code = detected_lang_code
        if manual_hint != "Auto-detect":
            # Extract code from inside parentheses
            if "(" in manual_hint and ")" in manual_hint:
                active_lang_code = manual_hint.split("(")[-1].replace(")", "").strip().lower()

        # Hybrid Search relational filter controls
        f_col1, f_col2, f_col3 = st.columns(3)
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
        with f_col3:
            # Get distinct language codes present in the seed data
            seed_langs = sorted(list({t["language_code"] for t in tickets}))
            lang_filter_opts = ["All"] + [f"{get_language_flag(c)} {c.upper()}" for c in seed_langs]
            selected_lang_filter_label = st.selectbox(
                "Target Language:",
                options=lang_filter_opts,
                help="Filter target tickets by language, or select 'All' for cross-lingual discovery.",
            )
            if selected_lang_filter_label == "All":
                target_lang_filter = "All"
            else:
                target_lang_filter = selected_lang_filter_label.split()[-1].lower()

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
                with st.spinner("Embedding text and searching multilingual vector store..."):
                    query_vec = generate_embedding(active_query)
                    results = find_similar_in_memory(
                        query_vec,
                        tickets,
                        top_n=3,
                        category_filter=category_filter,
                        priority_filter=priority_filter,
                        language_filter=target_lang_filter,
                    )
                elapsed_ms = (time.time() - start_time) * 1000.0

                filter_info = []
                if category_filter != "All":
                    filter_info.append(f"Category: `{category_filter}`")
                if priority_filter != "All":
                    filter_info.append(f"Priority: `{priority_filter}`")
                if target_lang_filter != "All":
                    filter_info.append(f"Language: `{target_lang_filter.upper()}`")
                filter_suffix = f"  |  Filter: {', '.join(filter_info)}" if filter_info else ""

                st.caption(f"Found {len(results)} matching tickets in {elapsed_ms:.1f} ms{filter_suffix}")

                if not results:
                    st.info(
                        f"No tickets found matching the filters (Category: `{category_filter}`, Priority: `{priority_filter}`, Language: `{target_lang_filter}`). "
                        "Try setting filters to 'All'."
                    )
                else:
                    for rank, match in enumerate(results, start=1):
                        score = float(match.get("similarity_score") or 0.0)
                        percent = max(0.0, min(100.0, score * 100.0))
                        ticket_id = match.get("ticket_id")
                        ticket_lang = str(match.get("language_code", "en")).lower()
                        category = match.get("category_name", "General")
                        priority = match.get("priority", "MEDIUM")

                        if percent >= 80.0:
                            conf_badge = "High"
                        elif percent >= 65.0:
                            conf_badge = "Moderate"
                        else:
                            conf_badge = "Low"

                        with st.container(border=True):
                            lang_flag = get_language_flag(ticket_lang)
                            lang_name = get_language_name(ticket_lang)
                            st.markdown(
                                f"**#{rank} &middot; Ticket `{ticket_id}`** &nbsp;|&nbsp; "
                                f"Language: **{lang_flag} {lang_name} ({ticket_lang.upper()})** &nbsp;|&nbsp; "
                                f"Category: **{category}** &nbsp;|&nbsp; "
                                f"Priority: `{priority}` &nbsp;|&nbsp; "
                                f"Confidence: `{conf_badge}`"
                            )
                            st.progress(percent / 100.0)
                            st.caption(f"Similarity score: **{percent:.1f}%** (Cosine distance: {float(match.get('similarity_distance') or 0):.4f})")

                            # Highlight cross-lingual discovery
                            if active_lang_code.lower() != ticket_lang:
                                q_flag = get_language_flag(active_lang_code)
                                q_name = get_language_name(active_lang_code)
                                st.info(
                                    f"🌐 **Cross-Lingual Match**: Query in **{q_flag} {q_name}** matched resolution stored in **{lang_flag} {lang_name}**!"
                                )

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
                        if target_lang_filter != "All":
                            where_parts.append(f"t.language_code = '{target_lang_filter}'")
                        where_sql = "\n  AND ".join(where_parts)
                        st.code(
                            f"""-- Oracle Database 23ai Hybrid Vector + Relational Query across 50+ Languages
SELECT t.ticket_id, t.description, t.resolution, t.language_code, c.category_name, t.priority,
       VECTOR_DISTANCE(t.description_embedding, :query_vector, COSINE) AS distance
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
                st.markdown("#### Ready to Search across 50+ Languages")
                st.write(
                    "Enter a customer issue on the left in any language (English, Spanish, French, German, Japanese, Arabic, Russian, Hindi, Tamil, etc.) "
                    "or choose a sample query from the dropdown to run cross-lingual semantic similarity search."
                )


if __name__ == "__main__":
    main()
