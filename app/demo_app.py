"""
Resolvix — Multilingual Agentic RAG Dashboard (Streamlit).

Dual-mode Oracle 23ai / in-memory retrieval + local Ollama agent for
classification, grounded synthesis, localization, and 1-click ticket filing.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from agent.llm_client import OllamaClient
from agent.resolver import AgentResult, TicketResolverAgent
from db.connection import is_db_available
from embeddings.generate import generate_embedding, get_model
from embeddings.languages import detect_language, get_language_display
from embeddings.similarity_search import file_new_ticket

st.set_page_config(
    page_title="Resolvix — Agentic RAG Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container { max-width: 1280px; padding-top: 1.25rem; padding-bottom: 2.5rem; }
    .resolution-card {
        background-color: #f0fdf4;
        border-left: 4px solid #16a34a;
        padding: 14px 16px;
        border-radius: 6px;
        margin: 8px 0 14px 0;
    }
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-right: 6px;
    }
    .badge-tech { background: #dbeafe; color: #1e40af; }
    .badge-billing { background: #fce7f3; color: #9d174d; }
    .badge-account { background: #e0e7ff; color: #3730a3; }
    .badge-security { background: #ffedd5; color: #9a3412; }
    .badge-general { background: #f3f4f6; color: #374151; }
    .badge-low { background: #ecfdf5; color: #065f46; }
    .badge-medium { background: #fef9c3; color: #854d0e; }
    .badge-high { background: #ffedd5; color: #9a3412; }
    .badge-critical { background: #fee2e2; color: #991b1b; }
    </style>
    """,
    unsafe_allow_html=True,
)

CATEGORY_BADGE = {
    "TECH": "badge-tech",
    "BILLING": "badge-billing",
    "ACCOUNT": "badge-account",
    "SECURITY": "badge-security",
    "GENERAL": "badge-general",
}
PRIORITY_BADGE = {
    "LOW": "badge-low",
    "MEDIUM": "badge-medium",
    "HIGH": "badge-high",
    "CRITICAL": "badge-critical",
}


@st.cache_resource
def load_embedding_model():
    return get_model()


@st.cache_data(ttl=15)
def fetch_health(model_name: str) -> dict:
    oracle_ok = is_db_available()
    client = OllamaClient(model=model_name)
    ollama_ok = client.is_available()
    models = client.list_models() if ollama_ok else []
    return {
        "oracle_ok": oracle_ok,
        "ollama_ok": ollama_ok,
        "models": models,
        "model": model_name,
    }


def _category_badge_html(category: str, priority: str) -> str:
    c = CATEGORY_BADGE.get(category, "badge-general")
    p = PRIORITY_BADGE.get(priority, "badge-medium")
    return (
        f'<span class="badge {c}">{category}</span>'
        f'<span class="badge {p}">{priority}</span>'
    )


def render_result_card(rank: int, match: dict) -> None:
    score = float(match.get("similarity_score") or 0.0)
    percent = float(match.get("similarity_pct") or max(0.0, min(100.0, score * 100.0)))
    with st.container(border=True):
        st.markdown(
            f"**#{rank} · Ticket `{match.get('ticket_id')}`** &nbsp;|&nbsp; "
            f"Language: `{str(match.get('language_code', '?')).upper()}` &nbsp;|&nbsp; "
            f"Category: **{match.get('category_name', '?')}** &nbsp;|&nbsp; "
            f"Priority: `{match.get('priority', '?')}`"
        )
        st.progress(min(1.0, percent / 100.0))
        st.caption(
            f"Similarity score: **{percent:.1f}%** "
            f"(Cosine distance: {float(match.get('similarity_distance') or 0):.4f})"
        )
        st.markdown("**Original Description:**")
        st.write(match.get("description") or "(empty)")
        st.markdown("**Historical Resolution:**")
        if match.get("resolution"):
            st.success(match["resolution"])
        else:
            st.info("No resolution text stored for this ticket.")


def main() -> None:
    st.title("Resolvix — Multilingual Agentic RAG")
    st.caption(
        "Oracle 23ai AI Vector Search · Local Ollama agent · Dual-mode resilient retrieval"
    )

    default_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    if "ollama_model" not in st.session_state:
        st.session_state["ollama_model"] = default_model
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    if "last_result" not in st.session_state:
        st.session_state["last_result"] = None
    if "selected_query" not in st.session_state:
        st.session_state["selected_query"] = ""
    if "feedback" not in st.session_state:
        st.session_state["feedback"] = None

    # Sidebar diagnostics
    with st.sidebar:
        st.header("System Diagnostics")
        health = fetch_health(st.session_state["ollama_model"])

        if health["oracle_ok"]:
            st.success("Oracle 23ai: 🟢 Online (AI Vector Search)")
        else:
            st.error("Oracle 23ai: 🔴 Offline (In-Memory Fallback)")

        if health["ollama_ok"]:
            st.success(f"Ollama LLM: 🟢 Connected ({st.session_state['ollama_model']})")
        else:
            st.error("Ollama LLM: 🔴 Offline (extractive fallback)")

        model_options = health["models"] or [default_model]
        if st.session_state["ollama_model"] not in model_options:
            model_options = [st.session_state["ollama_model"], *model_options]
        st.session_state["ollama_model"] = st.selectbox(
            "Ollama model",
            options=model_options,
            index=model_options.index(st.session_state["ollama_model"]),
        )

        st.divider()
        st.subheader("Roadmap")
        st.caption("Multi-turn refine · Semantic incident clustering · HITL escalation")
        if st.button("Clear chat history"):
            st.session_state["chat_history"] = []
            st.session_state["last_result"] = None
            st.session_state["feedback"] = None
            st.rerun()

    try:
        load_embedding_model()
    except Exception as exc:
        st.warning(f"Embedding model not ready yet: {exc}")

    col_left, col_right = st.columns([1, 1.35], gap="large")

    with col_left:
        st.subheader("New Ticket Query")
        preset_choice = st.selectbox(
            "Load sample query:",
            options=[
                "— Custom input (type below) —",
                "Hindi: Password reset link expired (Login)",
                "English: Billed twice on monthly subscription (Billing)",
                "Tamil: Mobile app crash on splash screen (Technical)",
                "Spanish: No puedo iniciar sesión (Security)",
                "Japanese: アプリが起動直後にクラッシュします (Tech)",
            ],
        )
        preset_mapping = {
            "Hindi: Password reset link expired (Login)": (
                "मेरा पासवर्ड रीसेट नहीं हो रहा है — ईमेल में मिला रीसेट लिंक "
                "तुरंत समाप्त हो जाता है या अमान्य टोकन त्रुटि दिखाता है।"
            ),
            "English: Billed twice on monthly subscription (Billing)": (
                "I was charged twice for my monthly subscription on the same invoice "
                "and need the extra charge reversed."
            ),
            "Tamil: Mobile app crash on splash screen (Technical)": (
                "latest version-ல் mobile app splash screen-க்குப் பிறகு immediately "
                "crash ஆகிறது; tickets open செய்ய முடியவில்லை."
            ),
            "Spanish: No puedo iniciar sesión (Security)": (
                "No puedo iniciar sesión: el enlace de restablecimiento de contraseña "
                "caduca de inmediato o muestra un token inválido."
            ),
            "Japanese: アプリが起動直後にクラッシュします (Tech)": (
                "最新バージョンのモバイルアプリがスプラッシュ画面の直後にクラッシュし、"
                "チケットを開けません。"
            ),
        }
        if preset_choice in preset_mapping:
            st.session_state["selected_query"] = preset_mapping[preset_choice]

        query_text = st.text_area(
            "Issue description:",
            value=st.session_state["selected_query"],
            height=140,
            placeholder="Describe the issue in any language…",
        )

        detected = detect_language(query_text) if query_text.strip() else "en"
        st.caption(f"Detected language: {get_language_display(detected)}")

        lang_hint = st.selectbox(
            "Language hint:",
            options=["Auto-detect", "English", "Hindi", "Tamil", "Spanish", "Japanese", "German"],
            help="Override auto-detection when needed. Auto-detect uses embeddings/languages.py.",
        )
        lang_override_map = {
            "English": "en",
            "Hindi": "hi",
            "Tamil": "ta",
            "Spanish": "es",
            "Japanese": "ja",
            "German": "de",
        }
        language_override = lang_override_map.get(lang_hint)

        f1, f2 = st.columns(2)
        with f1:
            category_filter = st.selectbox(
                "Filter Category:",
                options=["All", "Billing", "Technical", "Login", "Account", "Refund", "General"],
            )
        with f2:
            priority_filter = st.selectbox(
                "Filter Priority:",
                options=["All", "URGENT", "HIGH", "MEDIUM", "LOW"],
            )

        b1, b2 = st.columns([2, 1])
        with b1:
            search_clicked = st.button(
                "Resolve with AI Agent", type="primary", use_container_width=True
            )
        with b2:
            if st.button("Clear", use_container_width=True):
                st.session_state["selected_query"] = ""
                st.session_state["last_result"] = None
                st.session_state["feedback"] = None
                st.rerun()

        st.divider()
        st.markdown("#### Refine & Clarify (multi-turn)")
        follow_up = st.text_input(
            "Follow-up question",
            placeholder="e.g. Simplify this for a non-technical user",
            key="follow_up_input",
        )
        refine_clicked = st.button("Ask follow-up", use_container_width=True)

    with col_right:
        st.subheader("Agent Resolution")
        result: AgentResult | None = st.session_state.get("last_result")

        run_query = None
        use_history = None
        if search_clicked:
            run_query = query_text.strip()
            use_history = None
            st.session_state["chat_history"] = []
        elif refine_clicked and result is not None and follow_up.strip():
            run_query = follow_up.strip()
            use_history = list(st.session_state["chat_history"]) + [
                {"role": "user", "content": result.query},
                {"role": "assistant", "content": result.synthesized_resolution},
            ]

        if run_query is not None:
            if not run_query:
                st.warning("Please enter a ticket description before searching.")
            else:
                with st.spinner("Running agent pipeline (embed → retrieve → classify → synthesize)…"):
                    try:
                        agent = TicketResolverAgent(
                            model=st.session_state["ollama_model"]
                        )
                        result = agent.resolve(
                            run_query,
                            top_n=3,
                            category_filter=None
                            if category_filter == "All"
                            else category_filter,
                            priority_filter=None
                            if priority_filter == "All"
                            else priority_filter,
                            language_override=language_override,
                            chat_history=use_history,
                        )
                        st.session_state["last_result"] = result
                        st.session_state["selected_query"] = query_text
                        st.session_state["chat_history"] = (use_history or []) + [
                            {"role": "user", "content": run_query},
                            {"role": "assistant", "content": result.synthesized_resolution},
                        ]
                        st.session_state["feedback"] = None
                    except Exception as exc:
                        st.error(
                            "Agent pipeline failed gracefully — check Oracle / Ollama health.\n\n"
                            f"Details: {exc}"
                        )
                        result = None

        if result is None:
            with st.container(border=True):
                st.markdown("#### Ready to resolve")
                st.write(
                    "Enter a customer issue on the left (any of 50+ languages) and click "
                    "**Resolve with AI Agent**. The system will retrieve similar tickets from "
                    "Oracle 23ai (or in-memory fallback) and synthesize a grounded resolution."
                )
            return

        # Status line
        backend_label = (
            "Oracle 23ai VECTOR_DISTANCE"
            if result.search_backend == "ORACLE_23AI"
            else "In-Memory cosine fallback"
        )
        st.caption(
            f"Backend: **{backend_label}** · Language: {result.detected_language_name} "
            f"({result.detected_language_code}) · Confidence: {result.confidence * 100:.1f}%"
        )
        st.markdown(
            _category_badge_html(result.classified_category, result.classified_priority),
            unsafe_allow_html=True,
        )
        if result.classification_reasoning:
            st.caption(f"Classification: {result.classification_reasoning}")

        if result.escalation_required:
            st.warning(result.escalation_hint or "ESCALATION_REQUIRED")

        # AI resolution card
        show_native = False
        if result.localized_resolution and result.detected_language_code != "en":
            tab_en, tab_native = st.tabs(
                ["Show English", f"Show {result.detected_language_name}"]
            )
            with tab_en:
                st.markdown(
                    f'<div class="resolution-card">{result.synthesized_resolution}</div>',
                    unsafe_allow_html=True,
                )
            with tab_native:
                st.markdown(
                    f'<div class="resolution-card">{result.localized_resolution}</div>',
                    unsafe_allow_html=True,
                )
                show_native = True
        else:
            st.markdown("**AI Synthesized Solution**")
            st.markdown(result.synthesized_resolution)

        copy_text = (
            result.localized_resolution
            if show_native and result.localized_resolution
            else result.synthesized_resolution
        )
        st.code(copy_text, language="markdown")

        fb1, fb2, fb3 = st.columns([1, 1, 2])
        with fb1:
            if st.button("👍 Helpful"):
                st.session_state["feedback"] = "up"
        with fb2:
            if st.button("👎 Not helpful"):
                st.session_state["feedback"] = "down"
        with fb3:
            if st.session_state.get("feedback") == "up":
                st.success("Thanks — feedback recorded.")
            elif st.session_state.get("feedback") == "down":
                st.info("Thanks — we'll use this to improve grounding.")

        # File ticket action
        st.divider()
        if st.button("File This as New Ticket in Oracle 23ai", type="secondary"):
            if not is_db_available():
                st.error("Oracle is offline — cannot file ticket right now.")
            else:
                with st.spinner("Inserting OPEN ticket…"):
                    emb = generate_embedding(result.query)
                    ticket_id = file_new_ticket(
                        description=result.query,
                        embedding=emb,
                        category_name=result.classified_category,
                        priority=result.classified_priority,
                        language_code=result.detected_language_code,
                        resolution=result.synthesized_resolution,
                    )
                if ticket_id:
                    st.success(f"Filed as ticket **#{ticket_id}** (status=OPEN).")
                    fetch_health.clear()
                else:
                    st.error("Insert failed — check DB credentials and FK seed data.")

        # Matched tickets
        st.subheader("Matched Reference Tickets")
        if not result.similar_tickets:
            st.info("No similar resolved/closed tickets found for this query/filter.")
        else:
            for rank, match in enumerate(result.similar_tickets, start=1):
                render_result_card(rank, match)

        # Trace + SQL
        with st.expander("Agent Reasoning & Tool Trace", expanded=False):
            for step in result.trace_steps:
                st.markdown(
                    f"- **{step.get('step')}** — {step.get('duration_ms')} ms — "
                    f"{step.get('details')}"
                )

        with st.expander("Live Oracle 23ai SQL", expanded=False):
            st.code(result.live_sql, language="sql")
            st.caption(
                "Executed when Oracle is online. Offline mode uses in-memory cosine "
                "over data/tickets_seed.csv instead."
            )


if __name__ == "__main__":
    main()
