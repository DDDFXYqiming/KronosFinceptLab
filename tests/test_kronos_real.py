"""Smoke test for real Kronos inference.

This test is skipped unless:
- torch is importable
- The upstream Kronos model package is importable (KRONOS_REPO_PATH or external/Kronos)
- HuggingFace models can be loaded (pre-cached or network available)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Add external/Kronos to sys.path for import check
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_KRONOS_REPO = Path(os.environ.get("KRONOS_REPO_PATH", str(_PROJECT_ROOT / "external" / "Kronos")))

_torch_available = False
_kronos_model_available = False

try:
    import torch  # noqa: F401
    _torch_available = True
except ImportError:
    pass

if _torch_available and _KRONOS_REPO.is_dir():
    _kronos_path = str(_KRONOS_REPO)
    if _kronos_path not in sys.path:
        sys.path.insert(0, _kronos_path)
    try:
        from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: F401
        _kronos_model_available = True
    except ImportError:
        pass

requires_kronos = pytest.mark.skipif(
    not (_torch_available and _kronos_model_available),
    reason="Real Kronos smoke test requires torch + upstream Kronos model package (set KRONOS_REPO_PATH or place at external/Kronos)",
)


@requires_kronos
def test_kronos_predictor_wrapper_loads_and_predicts():
    """Load Kronos-mini (smallest) and run a 1-step prediction on synthetic data."""
    import pandas as pd
    from kronos_fincept.predictor import KronosPredictorWrapper

    wrapper = KronosPredictorWrapper(
        model_id="NeoQuasar/Kronos-mini",
        tokenizer_id="NeoQuasar/Kronos-Tokenizer-2k",
        max_context=64,
    )

    timestamps = pd.date_range("2026-01-01", periods=50, freq="h")
    df = pd.DataFrame(
        {
            "open": [100.0 + i * 0.1 for i in range(50)],
            "high": [101.0 + i * 0.1 for i in range(50)],
            "low": [99.0 + i * 0.1 for i in range(50)],
            "close": [100.5 + i * 0.1 for i in range(50)],
            "volume": [1000.0] * 50,
            "amount": [100000.0] * 50,
        },
        index=timestamps,
    )
    x_timestamp = pd.Series(timestamps)

    result = wrapper.predict(df=df, x_timestamp=x_timestamp, pred_len=3)

    assert result.backend == "kronos"
    assert result.frame is not None
    assert len(result.frame) == 3
    assert all(col in result.frame.columns for col in ["open", "high", "low", "close"])


@requires_kronos
def test_kronos_repo_path_resolution():
    """Verify that KRONOS_REPO_PATH env var is respected."""
    from kronos_fincept.predictor import _resolve_kronos_repo

    repo = _resolve_kronos_repo()
    assert repo is not None
    assert (repo / "model" / "__init__.py").exists()
