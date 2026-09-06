"""Tests for multilingual embedding generation and cross-lingual similarity."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from embeddings.generate import generate_embedding

CSV_PATH = PROJECT_ROOT / "data" / "tickets_seed.csv"


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two 1-D vectors."""
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        raise ValueError("Cannot compute cosine similarity with a zero vector")
    return float(np.dot(a, b) / denom)


def test_generate_embedding_shape_and_dtype():
    """English sample should yield a float32 vector of length 384."""
    vector = generate_embedding(
        "Unable to reset my password — the reset link expires immediately."
    )
    assert vector.shape == (384,), f"Expected shape (384,), got {vector.shape}"
    assert vector.dtype == np.float32, f"Expected dtype float32, got {vector.dtype}"
    print(f"[PASS] shape={vector.shape}, dtype={vector.dtype}")


def test_generate_embedding_rejects_empty_and_none():
    """Empty string and None must raise ValueError."""
    with pytest.raises(ValueError):
        generate_embedding("")
    print("[PASS] generate_embedding('') raises ValueError")

    with pytest.raises(ValueError):
        generate_embedding(None)  # type: ignore[arg-type]
    print("[PASS] generate_embedding(None) raises ValueError")


def test_cross_lingual_translation_pairs_vs_unrelated():
    """Translation triples should cluster; unrelated tickets should not."""
    df = pd.read_csv(CSV_PATH)

    # Rows 0-2, 3-5, 6-8 are the deliberate en/hi/ta translation triples.
    triples = [
        ("password_reset", df.iloc[0:3]),
        ("double_charge", df.iloc[3:6]),
        ("app_crash", df.iloc[6:9]),
    ]

    print("\n=== Cross-lingual translation-pair cosine similarities ===")
    pair_scores: list[float] = []

    for label, group in triples:
        embeddings = {
            row.language_code: generate_embedding(row.description)
            for row in group.itertuples(index=False)
        }
        assert set(embeddings) == {"en", "hi", "ta"}, (
            f"{label}: expected en/hi/ta, got {sorted(embeddings)}"
        )

        for left, right in (("en", "hi"), ("en", "ta"), ("hi", "ta")):
            score = cosine_similarity(embeddings[left], embeddings[right])
            pair_scores.append(score)
            print(
                f"[{label}] {left}-{right} cosine similarity = {score:.4f}"
            )
            assert score > 0.7, (
                f"{label} {left}-{right} similarity {score:.4f} is not > 0.7"
            )

    # Unrelated: Login password-reset (en) vs Billing GST tax invoice (en),
    # different category and meaning.
    unrelated_a = df.iloc[0]   # Login / password reset (en)
    unrelated_b = df.iloc[12]  # Billing / GST tax twice (en)
    unrelated_score = cosine_similarity(
        generate_embedding(unrelated_a.description),
        generate_embedding(unrelated_b.description),
    )
    min_pair = min(pair_scores)
    mean_pair = float(np.mean(pair_scores))

    print("\n=== Unrelated pair (should be lower) ===")
    print(
        f"[unrelated] en(Login/password-reset) vs en(Billing/GST-tax) "
        f"cosine similarity = {unrelated_score:.4f}"
    )
    print(
        f"Translation-pair min={min_pair:.4f}, mean={mean_pair:.4f}; "
        f"unrelated={unrelated_score:.4f}"
    )

    assert unrelated_score < 0.5, (
        f"Unrelated similarity {unrelated_score:.4f} is not < 0.5"
    )
    assert unrelated_score < min_pair, (
        f"Unrelated score {unrelated_score:.4f} is not lower than "
        f"weakest translation pair {min_pair:.4f}"
    )
    print(
        "[PASS] Translation pairs > 0.7 and unrelated pair is meaningfully lower."
    )
