"""Analytics package — semantic clustering / incident detection (Feature B)."""

from analytics.clustering import (
    IncidentAlert,
    analyze_last_24h,
    analyze_last_24h_stub,
    cluster_recent_embeddings,
    detect_hourly_bursts,
    fetch_tickets_last_24h,
)

__all__ = [
    "IncidentAlert",
    "analyze_last_24h",
    "analyze_last_24h_stub",
    "cluster_recent_embeddings",
    "detect_hourly_bursts",
    "fetch_tickets_last_24h",
]
