"""
Streamlit frontend for the Ticket Similarity Finder.

Allows support agents to enter a query in any language and find
the most semantically similar resolved tickets using Oracle AI Vector Search.
"""

import os
import sys
import array

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.connection import get_connection
from embeddings.generate import generate_embedding


st.set_page_config(page_title="Ticket Similarity Finder", layout="wide")
st.title("🎫 Ticket Similarity Finder")
st.markdown("Enter a support query in any language to find similar resolved tickets.")

query = st.text_area("Describe the issue:", height=120)
top_k = st.slider("Number of results", min_value=1, max_value=20, value=5)

if st.button("Search") and query.strip():
    with st.spinner("Generating embedding and searching..."):
        query_embedding = generate_embedding(query)
        query_vector = array.array("f", query_embedding)

        conn = get_connection()
        cursor = conn.cursor()

        try:
            sql = """
                SELECT ticket_id, subject, description, status, priority, language,
                       VECTOR_DISTANCE(embedding, :1, COSINE) AS distance
                FROM tickets
                ORDER BY VECTOR_DISTANCE(embedding, :2, COSINE)
                FETCH FIRST :3 ROWS ONLY
            """
            cursor.execute(sql, [query_vector, query_vector, top_k])
            results = cursor.fetchall()

            if not results:
                st.warning("No similar tickets found.")
            else:
                for row in results:
                    tid, subj, desc, status, prio, lang, dist = row
                    similarity = round((1 - dist) * 100, 2)
                    with st.expander(f"[{status.upper()}] {subj} — {similarity}% match"):
                        st.markdown(f"**Ticket ID:** {tid}")
                        st.markdown(f"**Priority:** {prio} | **Language:** {lang}")
                        st.markdown(f"**Description:** {desc}")
        except Exception as e:
            st.error(f"Query failed: {e}")
        finally:
            cursor.close()
            conn.close()
