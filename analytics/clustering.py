"""Semantic outage & duplicate detection (roadmap Feature B).

Batch-analyzes recent tickets, clusters embeddings (DBSCAN / K-Means / greedy
cosine), and raises Emerging Major Incident alerts when dense duplicate bursts
appear (default: ≥5 tickets with cosine > 0.88 within a 1-hour window).
"""

from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ClusterMethod = Literal["dbscan", "kmeans", "greedy"]


@dataclass
class IncidentAlert:
    """Emerging major-incident signal from dense similar ticket clusters."""

    cluster_id: int
    ticket_ids: list[int]
    size: int
    avg_similarity: float
    message: str
    method: str = "greedy"
    window_hours: float | None = None
    sample_descriptions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _pairwise_cosine(normalized: np.ndarray) -> np.ndarray:
    return normalized @ normalized.T


def _avg_pairwise_similarity(sim: np.ndarray, members: list[int]) -> float:
    if len(members) < 2:
        return 1.0
    vals = [
        float(sim[a, b])
        for i, a in enumerate(members)
        for b in members[i + 1 :]
    ]
    return float(np.mean(vals)) if vals else 1.0


def _cluster_dbscan(
    normalized: np.ndarray,
    similarity_threshold: float,
    min_cluster_size: int,
) -> list[list[int]]:
    """DBSCAN on cosine distance (eps = 1 - similarity_threshold)."""
    from sklearn.cluster import DBSCAN

    eps = max(1e-6, 1.0 - float(similarity_threshold))
    labels = DBSCAN(
        eps=eps,
        min_samples=min_cluster_size,
        metric="cosine",
    ).fit_predict(normalized)

    groups: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        if int(label) < 0:
            continue  # noise
        groups.setdefault(int(label), []).append(idx)
    return [members for members in groups.values() if len(members) >= min_cluster_size]


def _cluster_kmeans(
    normalized: np.ndarray,
    min_cluster_size: int,
    n_clusters: int | None = None,
) -> list[list[int]]:
    """K-Means on embedding space; keep clusters meeting min size."""
    from sklearn.cluster import KMeans

    n = normalized.shape[0]
    if n < min_cluster_size:
        return []
    k = n_clusters or max(2, min(8, n // max(min_cluster_size, 1)))
    k = min(k, n)
    labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(normalized)
    groups: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        groups.setdefault(int(label), []).append(idx)
    return [members for members in groups.values() if len(members) >= min_cluster_size]


def _cluster_greedy(
    sim: np.ndarray,
    similarity_threshold: float,
    min_cluster_size: int,
) -> list[list[int]]:
    """Greedy cosine cliques (no sklearn dependency)."""
    n = sim.shape[0]
    visited: set[int] = set()
    clusters: list[list[int]] = []
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
            clusters.append(members)
    return clusters


def cluster_recent_embeddings(
    ticket_ids: list[int],
    embeddings: np.ndarray,
    similarity_threshold: float = 0.88,
    min_cluster_size: int = 5,
    method: ClusterMethod = "dbscan",
    descriptions: list[str] | None = None,
) -> list[IncidentAlert]:
    """Cluster recent ticket embeddings and flag dense duplicate bursts."""
    if embeddings is None or len(ticket_ids) == 0:
        return []

    matrix = np.asarray(embeddings, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[0] != len(ticket_ids):
        raise ValueError("embeddings must be shape (N, D) aligned with ticket_ids")

    normalized = _l2_normalize(matrix)
    sim = _pairwise_cosine(normalized)

    try:
        if method == "dbscan":
            groups = _cluster_dbscan(normalized, similarity_threshold, min_cluster_size)
            used_method = "dbscan"
        elif method == "kmeans":
            groups = _cluster_kmeans(normalized, min_cluster_size)
            used_method = "kmeans"
        else:
            groups = _cluster_greedy(sim, similarity_threshold, min_cluster_size)
            used_method = "greedy"
    except Exception:
        groups = _cluster_greedy(sim, similarity_threshold, min_cluster_size)
        used_method = "greedy"

    alerts: list[IncidentAlert] = []
    for cluster_id, members in enumerate(groups):
        avg = _avg_pairwise_similarity(sim, members)
        # For K-Means, still require density vs similarity threshold
        if used_method == "kmeans" and avg < similarity_threshold:
            continue
        ids = [int(ticket_ids[m]) for m in members]
        samples: list[str] = []
        if descriptions is not None:
            for m in members[:3]:
                text = str(descriptions[m] or "")
                samples.append(text if len(text) <= 120 else text[:120] + "…")
        alerts.append(
            IncidentAlert(
                cluster_id=cluster_id,
                ticket_ids=ids,
                size=len(ids),
                avg_similarity=avg,
                method=used_method,
                message=(
                    f"Emerging Major Incident Alert: {len(ids)} tickets with "
                    f"avg cosine {avg:.2f} ≥ {similarity_threshold} "
                    f"(possible regional/shared outage, method={used_method})."
                ),
                sample_descriptions=samples,
            )
        )
    return alerts


def detect_hourly_bursts(
    ticket_ids: list[int],
    embeddings: np.ndarray,
    created_at: list[datetime],
    similarity_threshold: float = 0.88,
    min_cluster_size: int = 5,
    window: timedelta = timedelta(hours=1),
) -> list[IncidentAlert]:
    """Flag ≥min_cluster_size near-duplicate tickets arriving within ``window``."""
    if not ticket_ids:
        return []
    if not (len(ticket_ids) == len(embeddings) == len(created_at)):
        raise ValueError("ticket_ids, embeddings, and created_at must align")

    matrix = _l2_normalize(np.asarray(embeddings, dtype=np.float32))
    sim = _pairwise_cosine(matrix)
    n = len(ticket_ids)
    order = sorted(range(n), key=lambda i: created_at[i])

    alerts: list[IncidentAlert] = []
    cluster_id = 0
    used: set[int] = set()

    for start_pos, i in enumerate(order):
        if i in used:
            continue
        window_end = created_at[i] + window
        members = [i]
        for j in order[start_pos + 1 :]:
            if created_at[j] > window_end:
                break
            if j in used:
                continue
            if float(sim[i, j]) >= similarity_threshold:
                members.append(j)
        if len(members) >= min_cluster_size:
            for m in members:
                used.add(m)
            avg = _avg_pairwise_similarity(sim, members)
            ids = [int(ticket_ids[m]) for m in members]
            alerts.append(
                IncidentAlert(
                    cluster_id=cluster_id,
                    ticket_ids=ids,
                    size=len(ids),
                    avg_similarity=avg,
                    method="hourly_burst",
                    window_hours=window.total_seconds() / 3600.0,
                    message=(
                        f"Emerging Major Incident Alert: {len(ids)} tickets with "
                        f"cosine > {similarity_threshold} within "
                        f"{window.total_seconds() / 3600:.0f}h "
                        f"(e.g. Regional SSO Outage)."
                    ),
                )
            )
            cluster_id += 1
    return alerts


def _vector_to_numpy(value: Any) -> np.ndarray | None:
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        return np.asarray(value, dtype=np.float32).reshape(-1)
    if isinstance(value, (list, tuple)):
        return np.asarray(value, dtype=np.float32).reshape(-1)
    try:
        return np.asarray(list(value), dtype=np.float32).reshape(-1)
    except Exception:
        return None


def fetch_tickets_last_24h(
    hours: float = 24.0,
) -> tuple[list[int], np.ndarray, list[datetime], list[str]]:
    """Load tickets created in the last ``hours`` that have embeddings.

    Tries Oracle 23ai first; falls back to the seed CSV with synthetic timestamps
    so offline demos still exercise the clustering path.
    """
    from db.connection import is_db_available

    if is_db_available():
        try:
            ids, matrix, times, descs = _fetch_from_oracle(hours=hours)
            if len(ids) > 0:
                return ids, matrix, times, descs
        except Exception:
            pass
    return _fetch_from_seed_csv(hours=hours)


def _fetch_from_oracle(
    hours: float = 24.0,
) -> tuple[list[int], np.ndarray, list[datetime], list[str]]:
    from db.connection import get_connection

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                ticket_id,
                description_embedding,
                created_date,
                DBMS_LOB.SUBSTR(description, 200, 1) AS description
            FROM tickets
            WHERE created_date >= SYSTIMESTAMP - NUMTODSINTERVAL(:hours, 'HOUR')
              AND description_embedding IS NOT NULL
            ORDER BY created_date DESC
            """,
            {"hours": float(hours)},
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    ids: list[int] = []
    vectors: list[np.ndarray] = []
    times: list[datetime] = []
    descs: list[str] = []
    for ticket_id, embedding, created, description in rows:
        vec = _vector_to_numpy(embedding)
        if vec is None or vec.shape[0] == 0:
            continue
        ids.append(int(ticket_id))
        vectors.append(vec)
        if created.tzinfo is None:
            times.append(created.replace(tzinfo=timezone.utc))
        else:
            times.append(created)
        text = description.read() if hasattr(description, "read") else description
        descs.append(str(text or ""))

    if not vectors:
        return [], np.empty((0, 384), dtype=np.float32), [], []
    return ids, np.vstack(vectors).astype(np.float32), times, descs


def _fetch_from_seed_csv(
    hours: float = 24.0,
) -> tuple[list[int], np.ndarray, list[datetime], list[str]]:
    """Offline corpus: embed seed CSV and stagger created_at across last hours."""
    import pandas as pd

    from embeddings.generate import generate_embeddings_batch

    csv_path = Path(__file__).resolve().parents[1] / "data" / "tickets_seed.csv"
    df = pd.read_csv(csv_path)
    texts = [str(r["description"]) for _, r in df.iterrows()]
    matrix = generate_embeddings_batch(texts)
    now = datetime.now(timezone.utc)
    n = len(texts)
    # Pack many near the end of the window so hourly burst detection can fire in demos
    times = [
        now - timedelta(hours=hours) + timedelta(minutes=(i * 3) % max(int(hours * 60), 1))
        for i in range(n)
    ]
    ids = [101 + i for i in range(n)]
    return ids, matrix, times, texts


def analyze_last_24h(
    hours: float = 24.0,
    similarity_threshold: float = 0.88,
    min_cluster_size: int = 5,
    method: ClusterMethod = "dbscan",
) -> dict[str, Any]:
    """Batch-analyze recent tickets and return clustering + hourly burst alerts."""
    ticket_ids, embeddings, created_at, descriptions = fetch_tickets_last_24h(hours)
    if len(ticket_ids) == 0:
        return {
            "status": "ok",
            "tickets_analyzed": 0,
            "method": method,
            "alerts": [],
            "hourly_burst_alerts": [],
            "message": "No tickets with embeddings found in the analysis window.",
        }

    cluster_alerts = cluster_recent_embeddings(
        ticket_ids,
        embeddings,
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
        method=method,
        descriptions=descriptions,
    )
    burst_alerts = detect_hourly_bursts(
        ticket_ids,
        embeddings,
        created_at,
        similarity_threshold=similarity_threshold,
        min_cluster_size=min_cluster_size,
        window=timedelta(hours=1),
    )
    return {
        "status": "ok",
        "tickets_analyzed": len(ticket_ids),
        "method": method,
        "similarity_threshold": similarity_threshold,
        "min_cluster_size": min_cluster_size,
        "alerts": [a.to_dict() for a in cluster_alerts],
        "hourly_burst_alerts": [a.to_dict() for a in burst_alerts],
        "message": (
            f"Analyzed {len(ticket_ids)} tickets; "
            f"{len(cluster_alerts)} cluster alert(s), "
            f"{len(burst_alerts)} hourly burst alert(s)."
        ),
    }


# Backward-compatible alias used by earlier scaffolds / tests
def analyze_last_24h_stub() -> dict[str, Any]:
    """Deprecated alias — calls the real analyzer."""
    return analyze_last_24h()
