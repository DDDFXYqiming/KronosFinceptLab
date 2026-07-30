"""Leakage-aware evaluation helpers for financial time series experiments."""

from .rolling import (
    build_compact_evaluation_manifest,
    build_evaluation_manifest,
    build_window_records,
    compare_candidate_to_baseline,
    composite_score,
    discover_universe,
    select_screen_candidate,
    summarize_prediction_rows,
)
from .splits import select_calendar_window_starts

__all__ = [
    "build_compact_evaluation_manifest",
    "build_evaluation_manifest",
    "build_window_records",
    "compare_candidate_to_baseline",
    "composite_score",
    "discover_universe",
    "select_screen_candidate",
    "summarize_prediction_rows",
    "select_calendar_window_starts",
]
