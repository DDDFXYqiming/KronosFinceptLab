"""Leakage-aware evaluation helpers for financial time series experiments."""

from .rolling import (
    build_evaluation_manifest,
    build_window_records,
    discover_universe,
    summarize_prediction_rows,
)

__all__ = [
    "build_evaluation_manifest",
    "build_window_records",
    "discover_universe",
    "summarize_prediction_rows",
]
