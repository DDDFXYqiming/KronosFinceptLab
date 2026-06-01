"""Read verified market-review artifacts from the source project cache."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from . import DataSource, DataSourceConfig


DEFAULT_MARKET_REVIEW_DIR = Path("external/stock-analysis-system/data/market_review")

ARTIFACT_FILES = {
    "dragon_tiger": "dragon_tiger.parquet",
    "dragon_tiger_seats": "dragon_tiger_seats.json",
    "limit_up": "limit_up.parquet",
    "limit_down": "limit_down.parquet",
    "sector_industry": "sector_industry.parquet",
    "sector_concept": "sector_concept.parquet",
    "stock_in": "stock_in.parquet",
    "stock_out": "stock_out.parquet",
    "stock_browser_in": "stock_browser_in.parquet",
    "stock_browser_out": "stock_browser_out.parquet",
    "north_top10_sh": "north_top10_browser__sh_top10.parquet",
    "north_top10_sz": "north_top10_browser__sz_top10.parquet",
    "south_top10_sh": "north_top10_browser__ggt_top10_sh.parquet",
    "south_top10_sz": "north_top10_browser__ggt_top10_sz.parquet",
}


class SourceProjectMarketCacheSource(DataSource):
    """Expose source-project market review parquet/json artifacts."""

    supported_endpoints = {"source_market_review"}

    def __init__(self, priority: int = 20):
        config = DataSourceConfig(
            name="source_market_cache",
            priority=priority,
            max_retries=1,
            retry_delay=0.0,
            timeout=5.0,
            circuit_break_threshold=3,
            circuit_break_duration=300,
            health_check_interval=300,
        )
        super().__init__(config)
        self.base_dir = _market_review_dir()

    def is_available(self) -> bool:
        return self.base_dir.is_dir() and super().is_available()

    def fetch(self, endpoint: str, **kwargs) -> dict[str, Any]:
        try:
            if endpoint != "source_market_review":
                return self._failure(f"unsupported source market cache endpoint: {endpoint}")
            if not self.is_available():
                return self._failure(f"source market review directory not found: {self.base_dir}")
            artifact = str(kwargs.get("artifact") or "summary").strip() or "summary"
            limit = _safe_int(kwargs.get("limit"), 500)
            date = str(kwargs.get("date") or "").strip() or _latest_review_date(self.base_dir)
            payload = _read_artifact(self.base_dir, date, artifact, limit=limit)
            return {
                "success": True,
                "data": payload["data"],
                "count": payload["count"],
                "source": self.config.name,
                "timestamp": int(datetime.now().timestamp()),
                "metadata": {
                    "date": date,
                    "artifact": artifact,
                    "path": str(payload["path"]),
                    "data_quality": "source_project_verified_market_cache",
                },
            }
        except Exception as exc:
            return self._failure(f"{type(exc).__name__}: {exc}")

    def _failure(self, message: str) -> dict[str, Any]:
        return {
            "success": False,
            "data": None,
            "error": message,
            "source": self.config.name,
            "timestamp": int(datetime.now().timestamp()),
        }


def _market_review_dir() -> Path:
    raw = os.environ.get("STOCK_ANALYSIS_MARKET_REVIEW_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_MARKET_REVIEW_DIR


def _latest_review_date(base_dir: Path) -> str:
    dates = sorted(
        path.name for path in base_dir.iterdir()
        if path.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name)
    )
    if not dates:
        raise FileNotFoundError(f"no source market review date directories under {base_dir}")
    return dates[-1]


def _artifact_file_name(artifact: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", artifact):
        raise ValueError("artifact must contain only letters, numbers, and underscores")
    return ARTIFACT_FILES.get(artifact, f"{artifact}.parquet")


def _read_artifact(base_dir: Path, date: str, artifact: str, *, limit: int) -> dict[str, Any]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("date must use YYYY-MM-DD format")
    if artifact in {"summary", "overview", "manifest"}:
        return _read_review_summary(base_dir, date, limit=limit)
    file_name = _artifact_file_name(artifact)
    path = base_dir / date / file_name
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"data": data, "count": _json_count(data), "path": path}

    import pandas as pd

    frame = _read_parquet_frame(path, limit=limit)
    frame = frame.where(pd.notna(frame), None)
    records = frame.to_dict(orient="records")
    if limit > 0:
        records = records[:limit]
    return {"data": records, "count": len(records), "path": path}


def _read_review_summary(base_dir: Path, date: str, *, limit: int) -> dict[str, Any]:
    date_dir = base_dir / date
    if not date_dir.is_dir():
        raise FileNotFoundError(str(date_dir))

    artifacts: list[dict[str, Any]] = []
    for artifact, file_name in ARTIFACT_FILES.items():
        path = date_dir / file_name
        if not path.is_file():
            continue
        artifacts.append(
            {
                "artifact": artifact,
                "file": file_name,
                "kind": path.suffix.lower().lstrip("."),
                "count": _artifact_count(path),
                "path": str(path),
                "category": _artifact_category(artifact),
            }
        )
    artifacts.sort(key=lambda item: (str(item["category"]), str(item["artifact"])))
    if limit > 0:
        artifacts = artifacts[:limit]
    categories: dict[str, int] = {}
    for item in artifacts:
        category = str(item["category"])
        categories[category] = categories.get(category, 0) + 1
    return {
        "data": {
            "date": date,
            "base_dir": str(base_dir),
            "artifact_count": len(artifacts),
            "categories": categories,
            "artifacts": artifacts,
        },
        "count": len(artifacts),
        "path": date_dir,
    }


def _artifact_count(path: Path) -> int:
    if path.suffix.lower() == ".json":
        try:
            return _json_count(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return 0
    if path.suffix.lower() == ".parquet":
        try:
            import pyarrow.parquet as pq

            return int(pq.ParquetFile(path).metadata.num_rows)
        except Exception:
            pass
        try:
            import pandas as pd

            return int(len(pd.read_parquet(path, columns=[])))
        except Exception:
            return 0
    return 0


def _read_parquet_frame(path: Path, *, limit: int):
    if limit > 0:
        try:
            import pyarrow.parquet as pq

            parquet_file = pq.ParquetFile(path)
            batch = next(parquet_file.iter_batches(batch_size=limit), None)
            if batch is not None:
                return batch.to_pandas()
        except Exception:
            pass
    import pandas as pd

    return pd.read_parquet(path)


def _artifact_category(artifact: str) -> str:
    if artifact.startswith("sector_"):
        return "sector_flow"
    if artifact.startswith("stock_"):
        return "stock_flow"
    if artifact.startswith(("north_", "south_")):
        return "connect_flow"
    if artifact.startswith("dragon_tiger"):
        return "dragon_tiger"
    if artifact.startswith("limit_"):
        return "limit_board"
    return "other"


def _json_count(data: Any) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("data", "records", "items", "seats"):
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
        return len(data)
    return 1


def _safe_int(value: Any, default: int) -> int:
    try:
        return max(0, min(int(value), 5000))
    except (TypeError, ValueError):
        return default
