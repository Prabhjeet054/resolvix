"""Feedback loop — persist thumbs votes and improve retrieval."""

from feedback.store import (
    WEAK_SIMILARITY_THRESHOLD,
    apply_feedback_to_matches,
    feedback_stats,
    list_flagged_resolutions,
    record_feedback,
)

__all__ = [
    "WEAK_SIMILARITY_THRESHOLD",
    "apply_feedback_to_matches",
    "feedback_stats",
    "list_flagged_resolutions",
    "record_feedback",
]
