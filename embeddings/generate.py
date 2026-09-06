"""
Embedding generation for multilingual ticket text.

Uses sentence-transformers with paraphrase-multilingual-MiniLM-L12-v2.
This model maps semantically similar text across languages (English, Hindi,
Tamil, and others) into nearby points in the same 384-dimensional vector
space, which is why cross-lingual similarity search works: a Hindi or Tamil
ticket description can match an English resolution (and vice versa) without
translation, because their embeddings land close together under cosine
similarity / vector distance.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """Load and cache the multilingual SentenceTransformer singleton.

    The model is loaded once per process and reused on later calls so
    ingest and query paths do not pay the download/init cost repeatedly.
    """
    return SentenceTransformer(MODEL_NAME)


def generate_embedding(text: str) -> np.ndarray:
    """Encode a single text into a 384-dim float32 embedding.

    Whitespace is stripped/normalized. Empty or None input raises ValueError.

    Returns:
        np.ndarray of dtype float32 with shape (384,).

    Notes:
        paraphrase-multilingual-MiniLM-L12-v2 places semantically similar
        phrases from different languages (e.g. English / Hindi / Tamil) near
        each other in this shared vector space, enabling cross-lingual search.
    """
    if text is None:
        raise ValueError("text must be a non-empty string; got None")

    normalized = " ".join(str(text).split())
    if not normalized:
        raise ValueError("text must be a non-empty string after whitespace normalization")

    model = get_model()
    embedding = model.encode(normalized, normalize_embeddings=True)
    vector = np.asarray(embedding, dtype=np.float32).reshape(-1)

    if vector.shape != (EMBEDDING_DIM,):
        raise RuntimeError(
            f"Expected embedding shape ({EMBEDDING_DIM},), got {vector.shape}"
        )
    return vector


def generate_embeddings_batch(texts: list[str]) -> np.ndarray:
    """Batch-encode multiple texts into a (N, 384) float32 matrix.

    More efficient than calling generate_embedding() in a loop during CSV
    ingest, because SentenceTransformer.encode processes the batch together.

    Args:
        texts: List of ticket description (or other) strings.

    Returns:
        np.ndarray of dtype float32 with shape (len(texts), 384).

    Notes:
        Same cross-lingual property as generate_embedding(): similar meaning
        across English/Hindi/Tamil maps to nearby vectors in one space.
    """
    if texts is None:
        raise ValueError("texts must be a list of strings; got None")
    if not isinstance(texts, list):
        raise TypeError(f"texts must be a list, got {type(texts).__name__}")

    normalized = []
    for index, text in enumerate(texts):
        if text is None:
            raise ValueError(f"texts[{index}] is None; expected a non-empty string")
        cleaned = " ".join(str(text).split())
        if not cleaned:
            raise ValueError(
                f"texts[{index}] is empty after whitespace normalization"
            )
        normalized.append(cleaned)

    if not normalized:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32)

    model = get_model()
    embeddings = model.encode(
        normalized,
        normalize_embeddings=True,
        show_progress_bar=len(normalized) > 1,
    )
    matrix = np.asarray(embeddings, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)

    expected = (len(normalized), EMBEDDING_DIM)
    if matrix.shape != expected:
        raise RuntimeError(f"Expected embedding batch shape {expected}, got {matrix.shape}")
    return matrix


if __name__ == "__main__":
    sample = "Unable to reset my password — the reset link expires immediately."
    vector = generate_embedding(sample)
    print(f"sample: {sample!r}")
    print(f"shape: {vector.shape}")
    print(f"dtype: {vector.dtype}")
