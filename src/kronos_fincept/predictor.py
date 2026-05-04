"""Kronos predictor wrappers.

The module provides a deterministic dry-run predictor for integration tests and a
lazy real Kronos predictor hook for environments where the upstream Kronos code
and model dependencies are installed.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kronos_fincept.data_adapter import make_future_timestamps
from kronos_fincept.logging_config import log_event
from kronos_fincept.schemas import DEFAULT_MODEL_ID, DEFAULT_TOKENIZER_ID

_KRONOS_REPO_ENV = "KRONOS_REPO_PATH"
_PREDICTOR_CACHE_LOCK = threading.RLock()
_INFERENCE_LOCK = threading.Lock()
_PREDICTOR_CACHE: dict[tuple[str, str, int, str], "_CachedPredictor"] = {}
logger = logging.getLogger("kronos_fincept.predictor")


def _resolve_kronos_repo() -> Path | None:
    """Resolve the upstream Kronos repo path from env or well-known locations."""
    env = os.environ.get(_KRONOS_REPO_ENV)
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    # Check well-known project-local location
    here = Path(__file__).resolve().parents[3]  # project root
    local = here / "external" / "Kronos"
    if local.is_dir():
        return local
    return None


def _ensure_kronos_on_syspath() -> None:
    """Insert the upstream Kronos repo root into sys.path so `from model import ...` works."""
    repo = _resolve_kronos_repo()
    if repo is None:
        return
    repo_str = str(repo)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)


def _hf_cache_hint(model_id: str) -> str:
    """Return a hint about HuggingFace cache location."""
    hf_home = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
    return (
        f"HuggingFace model '{model_id}' not found or download failed. "
        f"Cache location: {hf_home}. "
        f"To use a local model directory, pass its path as model_id. "
        f"For offline usage, set HF_HUB_OFFLINE=1 and ensure models are pre-downloaded."
    )


@dataclass(frozen=True)
class ForecastResult:
    """Structured forecast output."""

    frame: pd.DataFrame
    device: str
    elapsed_ms: int
    backend: str
    model_cached: bool = False
    cache_key: str = ""
    load_wait_ms: int = 0
    inference_wait_ms: int = 0


@dataclass(frozen=True)
class ProbabilisticForecastResult:
    """Probabilistic forecast output from Monte Carlo sampling.

    Contains statistics computed from multiple sample paths.
    """

    # Single mean path (same as ForecastResult.frame)
    mean_frame: pd.DataFrame
    # Raw sample paths: list of DataFrames, one per sample
    samples: list[pd.DataFrame]
    # Statistics
    upside_probability: float  # P(final close > current close)
    volatility_amplification: float  # predicted vol / historical vol
    forecast_range: tuple[float, float]  # (min_final_close, max_final_close)
    mean_final_close: float
    # Metadata
    device: str
    elapsed_ms: int
    backend: str
    sample_count: int
    model_cached: bool = False
    cache_key: str = ""
    load_wait_ms: int = 0
    inference_wait_ms: int = 0


@dataclass(frozen=True)
class _CachedPredictor:
    predictor: Any
    device: str


def clear_predictor_cache() -> None:
    """Clear the process-level Kronos predictor cache.

    This is primarily used by tests and controlled local troubleshooting. Runtime
    code should keep the cache hot so Web forecast and Agent analysis reuse the
    same loaded model.
    """
    with _PREDICTOR_CACHE_LOCK:
        _PREDICTOR_CACHE.clear()


def predictor_cache_stats() -> dict[str, Any]:
    """Return lightweight cache diagnostics without touching Torch."""
    with _PREDICTOR_CACHE_LOCK:
        return {
            "size": len(_PREDICTOR_CACHE),
            "keys": ["|".join(str(part) for part in key) for key in _PREDICTOR_CACHE],
        }


def prewarm_predictor(
    *,
    model_id: str = DEFAULT_MODEL_ID,
    tokenizer_id: str = DEFAULT_TOKENIZER_ID,
    max_context: int = 512,
    device: str | None = None,
) -> dict[str, Any]:
    """Load the configured Kronos predictor into the process cache without inference."""
    started = time.perf_counter()
    wrapper = KronosPredictorWrapper(
        model_id=model_id,
        tokenizer_id=tokenizer_id,
        max_context=max_context,
        device=device,
    )
    try:
        wrapper._load()
    except Exception:
        log_event(
            logger,
            logging.ERROR,
            "kronos.model.prewarm_failure",
            "Kronos predictor prewarm failed",
            model_id=model_id,
            tokenizer_id=tokenizer_id,
            cache_key=wrapper.cache_key,
            duration_ms=int((time.perf_counter() - started) * 1000),
            exc_info=True,
        )
        raise
    stats = {
        "model_id": model_id,
        "tokenizer_id": tokenizer_id,
        "cache_key": wrapper.cache_key,
        "device": wrapper._resolved_device,
        "model_cached": wrapper._model_cached,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
    log_event(
        logger,
        logging.INFO,
        "kronos.model.prewarm_success",
        "Kronos predictor prewarmed",
        **stats,
        duration_ms=stats["elapsed_ms"],
    )
    return stats


class DryRunPredictor:
    """Deterministic predictor used before real Kronos dependencies are available."""

    def predict(self, df: pd.DataFrame, x_timestamp: pd.Series, pred_len: int) -> ForecastResult:
        started = time.perf_counter()
        y_timestamp = make_future_timestamps(x_timestamp, pred_len)
        last = df.iloc[-1]
        rows: list[dict[str, Any]] = []
        for index, timestamp in enumerate(y_timestamp, start=1):
            drift = 1.0 + index * 0.001
            close = float(last["close"]) * drift
            open_price = float(last["close"]) * (1.0 + (index - 1) * 0.001)
            high = max(open_price, close) * 1.002
            low = min(open_price, close) * 0.998
            rows.append(
                {
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": float(last.get("volume", 0.0)),
                    "amount": float(last.get("amount", 0.0)),
                }
            )
        frame = pd.DataFrame(rows)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return ForecastResult(frame=frame, device="cpu", elapsed_ms=elapsed_ms, backend="dry_run")


class KronosPredictorWrapper:
    """Lazy wrapper around upstream Kronos classes.

    Resolution order for the upstream `model` package:
      1. ``KRONOS_REPO_PATH`` env var (absolute path to the Kronos repo root)
      2. ``external/Kronos`` in the project tree
      3. ``PYTHONPATH`` must already contain the Kronos root
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        tokenizer_id: str = DEFAULT_TOKENIZER_ID,
        max_context: int = 512,
        device: str | None = None,
        temperature: float = 1.0,
        top_k: int = 0,
        top_p: float = 0.9,
        sample_count: int = 1,
    ) -> None:
        self.model_id = model_id
        self.tokenizer_id = tokenizer_id
        self.max_context = max_context
        self.device = device
        self.temperature = temperature
        self.top_k = top_k
        self.top_p = top_p
        self.sample_count = sample_count
        self._predictor: Any | None = None
        self._resolved_device = device or "auto"
        self._model_cached = False
        self._load_wait_ms = 0
        self._cache_key = (
            self.model_id,
            self.tokenizer_id,
            self.max_context,
            self.device or "auto",
        )

    @property
    def cache_key(self) -> str:
        return "|".join(str(part) for part in self._cache_key)

    def _load(self) -> Any:
        if self._predictor is not None:
            self._model_cached = True
            return self._predictor

        wait_started = time.perf_counter()
        log_event(
            logger,
            logging.INFO,
            "kronos.model.lock_wait_start",
            "Waiting for Kronos model cache lock",
            model_id=self.model_id,
            tokenizer_id=self.tokenizer_id,
            cache_key=self.cache_key,
        )
        _PREDICTOR_CACHE_LOCK.acquire()
        self._load_wait_ms = int((time.perf_counter() - wait_started) * 1000)
        if self._load_wait_ms:
            log_event(
                logger,
                logging.INFO,
                "kronos.model.lock_wait_done",
                "Kronos model cache lock acquired",
                model_id=self.model_id,
                tokenizer_id=self.tokenizer_id,
                cache_key=self.cache_key,
                duration_ms=self._load_wait_ms,
            )
        try:
            cached = _PREDICTOR_CACHE.get(self._cache_key)
            if cached is not None:
                self._predictor = cached.predictor
                self._resolved_device = cached.device
                self._model_cached = True
                log_event(
                    logger,
                    logging.INFO,
                    "kronos.model.cache_hit",
                    "Reusing cached Kronos predictor",
                    model_id=self.model_id,
                    tokenizer_id=self.tokenizer_id,
                    cache_key=self.cache_key,
                    device=self._resolved_device,
                )
                return self._predictor

            load_started = time.perf_counter()
            log_event(
                logger,
                logging.INFO,
                "kronos.model.load_start",
                "Loading Kronos predictor",
                model_id=self.model_id,
                tokenizer_id=self.tokenizer_id,
                cache_key=self.cache_key,
            )
            try:
                predictor, device = self._load_uncached()
            except Exception:
                log_event(
                    logger,
                    logging.ERROR,
                    "kronos.model.load_failure",
                    "Failed to load Kronos predictor",
                    model_id=self.model_id,
                    tokenizer_id=self.tokenizer_id,
                    cache_key=self.cache_key,
                    duration_ms=int((time.perf_counter() - load_started) * 1000),
                    exc_info=True,
                )
                raise
            self._predictor = predictor
            self._resolved_device = device
            self._model_cached = False
            _PREDICTOR_CACHE[self._cache_key] = _CachedPredictor(predictor=predictor, device=device)
            log_event(
                logger,
                logging.INFO,
                "kronos.model.load_success",
                "Kronos predictor loaded and cached",
                model_id=self.model_id,
                tokenizer_id=self.tokenizer_id,
                cache_key=self.cache_key,
                device=device,
                duration_ms=int((time.perf_counter() - load_started) * 1000),
            )
            return self._predictor
        finally:
            _PREDICTOR_CACHE_LOCK.release()

    def _load_uncached(self) -> tuple[Any, str]:
        _ensure_kronos_on_syspath()

        try:
            import torch  # noqa: F401
            from model import Kronos, KronosPredictor, KronosTokenizer
        except ImportError as exc:
            repo = _resolve_kronos_repo()
            hint_parts = [
                "Real Kronos inference requires the upstream Kronos package and torch/huggingface-hub.",
                "Resolution order:",
                f"  1. Set env KRONOS_REPO_PATH=<path-to-Kronos-repo>  (current: {os.environ.get(_KRONOS_REPO_ENV, 'unset')})",
                f"  2. Place Kronos at external/Kronos in the project root  (found: {repo is not None})",
                "  3. Add the Kronos root to PYTHONPATH manually",
                "Use dry_run=true for contract tests without Kronos installed.",
            ]
            raise RuntimeError("\n".join(hint_parts)) from exc

        try:
            from huggingface_hub import hf_hub_download  # noqa: F401
        except ImportError:
            pass  # will fail at from_pretrained time with a clear error

        device = self.device or ("cuda:0" if torch.cuda.is_available() else "cpu")

        # Try local model first (in external/ directory)
        project_root = Path(__file__).resolve().parents[2]
        local_model_dir = project_root / "external" / self.model_id.split("/")[-1]
        local_tokenizer_dir = project_root / "external" / self.tokenizer_id.split("/")[-1]

        try:
            if local_tokenizer_dir.is_dir():
                tokenizer = KronosTokenizer.from_pretrained(str(local_tokenizer_dir))
            else:
                tokenizer = KronosTokenizer.from_pretrained(self.tokenizer_id)
        except Exception as exc:
            raise RuntimeError(_hf_cache_hint(self.tokenizer_id)) from exc

        try:
            if local_model_dir.is_dir():
                model = Kronos.from_pretrained(str(local_model_dir))
            else:
                model = Kronos.from_pretrained(self.model_id)
        except Exception as exc:
            raise RuntimeError(_hf_cache_hint(self.model_id)) from exc

        model.to(device)
        model.eval()
        predictor = KronosPredictor(model, tokenizer, max_context=self.max_context, device=device)
        return predictor, device

    def predict(self, df: pd.DataFrame, x_timestamp: pd.Series, pred_len: int) -> ForecastResult:
        started = time.perf_counter()
        predictor = self._load()
        y_timestamp = make_future_timestamps(x_timestamp, pred_len)
        wait_started = time.perf_counter()
        _INFERENCE_LOCK.acquire()
        inference_wait_ms = int((time.perf_counter() - wait_started) * 1000)
        log_event(
            logger,
            logging.INFO,
            "kronos.inference.start",
            "Running Kronos inference",
            model_id=self.model_id,
            cache_key=self.cache_key,
            pred_len=pred_len,
            sample_count=self.sample_count,
            inference_wait_ms=inference_wait_ms,
        )
        try:
            frame = predictor.predict(
                df=df,
                x_timestamp=x_timestamp,
                y_timestamp=y_timestamp,
                pred_len=pred_len,
                T=self.temperature,
                top_k=self.top_k,
                top_p=self.top_p,
                sample_count=self.sample_count,
                verbose=False,
            )
            log_event(
                logger,
                logging.INFO,
                "kronos.inference.success",
                "Kronos inference completed",
                model_id=self.model_id,
                cache_key=self.cache_key,
                pred_len=pred_len,
                sample_count=self.sample_count,
                duration_ms=int((time.perf_counter() - started) * 1000),
                inference_wait_ms=inference_wait_ms,
            )
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                "kronos.inference.failure",
                "Kronos inference failed",
                model_id=self.model_id,
                cache_key=self.cache_key,
                pred_len=pred_len,
                sample_count=self.sample_count,
                duration_ms=int((time.perf_counter() - started) * 1000),
                inference_wait_ms=inference_wait_ms,
                exc_info=True,
            )
            raise
        finally:
            _INFERENCE_LOCK.release()
        frame = frame.reset_index(drop=False)
        if "timestamp" not in frame.columns:
            frame.insert(0, "timestamp", y_timestamp.reset_index(drop=True))
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return ForecastResult(
            frame=frame,
            device=self._resolved_device,
            elapsed_ms=elapsed_ms,
            backend="kronos",
            model_cached=self._model_cached,
            cache_key=self.cache_key,
            load_wait_ms=self._load_wait_ms,
            inference_wait_ms=inference_wait_ms,
        )

    def predict_probabilistic(
        self,
        df: pd.DataFrame,
        x_timestamp: pd.Series,
        pred_len: int,
        historical_volatility: float | None = None,
    ) -> ProbabilisticForecastResult:
        """Run Monte Carlo sampling and compute probabilistic statistics.

        Args:
            df: Historical OHLCV data
            x_timestamp: Timestamps for historical data
            pred_len: Number of bars to predict
            historical_volatility: Pre-computed historical volatility (annualized).
                                   If None, computed from df['close'].

        Returns:
            ProbabilisticForecastResult with statistics from multiple sample paths.
        """
        started = time.perf_counter()
        predictor = self._load()
        y_timestamp = make_future_timestamps(x_timestamp, pred_len)

        # Compute historical volatility if not provided
        if historical_volatility is None:
            returns = df["close"].pct_change().dropna()
            if len(returns) > 1:
                historical_volatility = float(returns.std() * np.sqrt(252))
            else:
                historical_volatility = 0.0

        # Run multiple samples
        samples: list[pd.DataFrame] = []
        final_closes: list[float] = []

        wait_started = time.perf_counter()
        _INFERENCE_LOCK.acquire()
        inference_wait_ms = int((time.perf_counter() - wait_started) * 1000)
        log_event(
            logger,
            logging.INFO,
            "kronos.inference.start",
            "Running Kronos probabilistic inference",
            model_id=self.model_id,
            cache_key=self.cache_key,
            pred_len=pred_len,
            sample_count=self.sample_count,
            inference_wait_ms=inference_wait_ms,
        )
        try:
            for i in range(self.sample_count):
                frame = predictor.predict(
                    df=df,
                    x_timestamp=x_timestamp,
                    y_timestamp=y_timestamp,
                    pred_len=pred_len,
                    T=self.temperature,
                    top_k=self.top_k,
                    top_p=self.top_p,
                    sample_count=1,  # Run one sample at a time for diversity
                    verbose=False,
                )
                frame = frame.reset_index(drop=False)
                if "timestamp" not in frame.columns:
                    frame.insert(0, "timestamp", y_timestamp.reset_index(drop=True))
                samples.append(frame)
                final_closes.append(float(frame.iloc[-1]["close"]))
            log_event(
                logger,
                logging.INFO,
                "kronos.inference.success",
                "Kronos probabilistic inference completed",
                model_id=self.model_id,
                cache_key=self.cache_key,
                pred_len=pred_len,
                sample_count=self.sample_count,
                duration_ms=int((time.perf_counter() - started) * 1000),
                inference_wait_ms=inference_wait_ms,
            )
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                "kronos.inference.failure",
                "Kronos probabilistic inference failed",
                model_id=self.model_id,
                cache_key=self.cache_key,
                pred_len=pred_len,
                sample_count=self.sample_count,
                duration_ms=int((time.perf_counter() - started) * 1000),
                inference_wait_ms=inference_wait_ms,
                exc_info=True,
            )
            raise
        finally:
            _INFERENCE_LOCK.release()

        # Compute statistics
        current_close = float(df.iloc[-1]["close"])
        final_closes_arr = np.array(final_closes)

        # Upside Probability: fraction of paths ending above current close
        upside_probability = float(np.mean(final_closes_arr > current_close))

        # Forecast Range: min and max final closes
        forecast_range = (float(np.min(final_closes_arr)), float(np.max(final_closes_arr)))

        # Mean final close
        mean_final_close = float(np.mean(final_closes_arr))

        # Volatility Amplification: predicted vol / historical vol
        if historical_volatility > 0:
            # Use returns from mean path
            mean_closes = np.mean([s["close"].values for s in samples], axis=0)
            mean_returns = np.diff(mean_closes) / mean_closes[:-1]
            predicted_volatility = float(np.std(mean_returns) * np.sqrt(252))
            volatility_amplification = predicted_volatility / historical_volatility
        else:
            volatility_amplification = 0.0

        # Mean path DataFrame
        mean_data: dict[str, Any] = {"timestamp": samples[0]["timestamp"].values}
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            if col in samples[0].columns:
                mean_data[col] = np.mean([s[col].values for s in samples], axis=0)
        mean_frame = pd.DataFrame(mean_data)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return ProbabilisticForecastResult(
            mean_frame=mean_frame,
            samples=samples,
            upside_probability=upside_probability,
            volatility_amplification=volatility_amplification,
            forecast_range=forecast_range,
            mean_final_close=mean_final_close,
            device=self._resolved_device,
            elapsed_ms=elapsed_ms,
            backend="kronos",
            sample_count=self.sample_count,
            model_cached=self._model_cached,
            cache_key=self.cache_key,
            load_wait_ms=self._load_wait_ms,
            inference_wait_ms=inference_wait_ms,
        )

    def predict_batch(
        self,
        dfs: list[pd.DataFrame],
        x_timestamps: list[pd.Series],
        pred_len: int,
    ) -> list[ForecastResult]:
        """Run batch prediction on multiple assets using upstream Kronos predict_batch.

        This is more efficient than calling predict() separately for each asset,
        as it batches the inference operations.

        Args:
            dfs: List of historical OHLCV DataFrames
            x_timestamps: List of timestamp Series
            pred_len: Number of bars to predict

        Returns:
            List of ForecastResult in same order as input.
        """
        started = time.perf_counter()
        predictor = self._load()

        # Prepare batch inputs
        y_timestamps = [make_future_timestamps(ts, pred_len) for ts in x_timestamps]

        wait_started = time.perf_counter()
        _INFERENCE_LOCK.acquire()
        inference_wait_ms = int((time.perf_counter() - wait_started) * 1000)
        log_event(
            logger,
            logging.INFO,
            "kronos.inference.start",
            "Running Kronos batch inference",
            model_id=self.model_id,
            cache_key=self.cache_key,
            pred_len=pred_len,
            batch_size=len(dfs),
            sample_count=self.sample_count,
            inference_wait_ms=inference_wait_ms,
        )
        try:
            try:
                # Use upstream predict_batch
                frames = predictor.predict_batch(
                    df_list=dfs,
                    x_timestamp_list=x_timestamps,
                    y_timestamp_list=y_timestamps,
                    pred_len=pred_len,
                    T=self.temperature,
                    top_k=self.top_k,
                    top_p=self.top_p,
                    sample_count=self.sample_count,
                    verbose=False,
                )
            except Exception:
                # Fallback to sequential if upstream batch inference fails.
                frames = []
                for df, ts in zip(dfs, x_timestamps):
                    y_ts = make_future_timestamps(ts, pred_len)
                    frame = predictor.predict(
                        df=df,
                        x_timestamp=ts,
                        y_timestamp=y_ts,
                        pred_len=pred_len,
                        T=self.temperature,
                        top_k=self.top_k,
                        top_p=self.top_p,
                        sample_count=self.sample_count,
                        verbose=False,
                    )
                    frames.append(frame)
            log_event(
                logger,
                logging.INFO,
                "kronos.inference.success",
                "Kronos batch inference completed",
                model_id=self.model_id,
                cache_key=self.cache_key,
                pred_len=pred_len,
                batch_size=len(dfs),
                sample_count=self.sample_count,
                duration_ms=int((time.perf_counter() - started) * 1000),
                inference_wait_ms=inference_wait_ms,
            )
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                "kronos.inference.failure",
                "Kronos batch inference failed",
                model_id=self.model_id,
                cache_key=self.cache_key,
                pred_len=pred_len,
                batch_size=len(dfs),
                sample_count=self.sample_count,
                duration_ms=int((time.perf_counter() - started) * 1000),
                inference_wait_ms=inference_wait_ms,
                exc_info=True,
            )
            raise
        finally:
            _INFERENCE_LOCK.release()

        results: list[ForecastResult] = []
        for i, frame in enumerate(frames):
            frame = frame.reset_index(drop=False)
            if "timestamp" not in frame.columns:
                frame.insert(0, "timestamp", y_timestamps[i].reset_index(drop=True))
            results.append(ForecastResult(
                frame=frame,
                device=self._resolved_device,
                elapsed_ms=int((time.perf_counter() - started) * 1000),
                backend="kronos_batch",
                model_cached=self._model_cached,
                cache_key=self.cache_key,
                load_wait_ms=self._load_wait_ms,
                inference_wait_ms=inference_wait_ms,
            ))

        return results
