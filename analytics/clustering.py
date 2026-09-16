"""Semantic outage & duplicate detection scaffolds (roadmap Feature B)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class IncidentAlert:
    """Emerging major-incident signal from dense similar ticket clusters."""

    cluster_id: int
    ticket_ids: list[int]
    size: int
    avg_similarity: float
    message: str


def cluster_recent_embeddings(
    ticket_ids: list[int],
    embeddings: np.ndarray,
    similarity_threshold: float = 0.88,
    min_cluster_size: int = 5,
) -> list[IncidentAlert]:
    """Cluster recent ticket embeddings and flag dense duplicate bursts.

    Scaffold implementation using greedy cosine grouping. Swap in DBSCAN /
    HDBSCAN for production-scale volumes when needed.
    """
    if embeddings is None or len(ticket_ids) == 0:
        return []

    matrix = np.asarray(embeddings, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] != len(ticket_ids):
        raise ValueError("embeddings must be shape (N, D) aligned with ticket_ids")

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = matrix / norms
    sim = normalized @ normalized.T

    n = sim.shape[0]
    visited: set[int] = set()
    alerts: list[IncidentAlert] = []
    cluster_id = 0

    for i in range(n):
        if i in visited:
            continue
        members = [i]
        for j in range(i + 1, n):
            if j in visited:
                continue
            if float(sim[i, j]) >= similarity_threshold:
                members.append(j)
        if len(members) >= min_cluster_size:
            for m in members:
                visited.add(m)
            pairwise = [
                float(sim[a, b])
                for a_idx, a in enumerate(members)
                for b in members[a_idx + 1 :]
            ]
            avg = float(np.mean(pairwise)) if pairwise else 1.0
            ids = [int(ticket_ids[m]) for m in members]
            alerts.append(
                IncidentAlert(
                    cluster_id=cluster_id,
                    ticket_ids=ids,
                    size=len(ids),
                    avg_similarity=avg,
                    message=(
                        f"Emerging Major Incident Alert: {len(ids)} tickets with "
                        f"avg cosine {avg:.2f} ≥ {similarity_threshold} "
                        f"(possible regional/shared outage)."
                    ),
                )
            )
            cluster_id += 1

    return alerts


def analyze_last_24h_stub() -> dict[str, Any]:
    """Placeholder entrypoint for batch outage detection jobs."""
    return {
        "status": "not_implemented",
        "hint": (
            "Load last-24h ticket embeddings from Oracle and call "
            "cluster_recent_embeddings()."
        ),
        "alerts": [],
    }
