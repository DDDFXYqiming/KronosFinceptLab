"""In-process job endpoints for slow forecast, analysis, and batch operations."""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from kronos_fincept.api.models import BacktestRequestIn, BatchForecastItemIn, BatchForecastRequestIn, ForecastRequestIn
from kronos_fincept.api.routes.ai_analyze import AgentAnalyzeRequest
from kronos_fincept.api.routes.batch import _item_to_forecast_request
from kronos_fincept.api.routes.data import fetch_market_rows_for_batch
from kronos_fincept.runtime_store import get_runtime_store
from kronos_fincept.schemas import ForecastRequest
from kronos_fincept.service import batch_forecast_from_requests, forecast_from_request

router = APIRouter(prefix="/jobs", tags=["jobs"])

_MAX_JOBS = 100
_JOB_TTL_SECONDS = 3600
_JOBS: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


class JobSubmitResponse(BaseModel):
    ok: bool = True
    job_id: str
    status: str


class JobCancelResponse(BaseModel):
    ok: bool = True
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    ok: bool = True
    job_id: str
    kind: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    steps: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float
    updated_at: float


class JobHistoryResponse(BaseModel):
    ok: bool = True
    jobs: list[JobStatusResponse]
    total: int


class BatchJobRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=100)
    market: str = Field(default="cn", min_length=1, max_length=16)
    start_date: str = Field(default="20250101", min_length=8, max_length=8)
    end_date: str = Field(..., min_length=8, max_length=8)
    adjust: str = Field(default="qfq", max_length=8)
    pred_len: int = Field(default=5, ge=1, le=60)
    model_id: str | None = Field(default=None, max_length=64)
    dry_run: bool = False
    start_immediately: bool = True


class BacktestJobRequest(BacktestRequestIn):
    start_immediately: bool = True


def _cleanup_jobs(now: float | None = None) -> None:
    now = now or time.time()
    try:
        get_runtime_store().prune_jobs(_MAX_JOBS, _JOB_TTL_SECONDS)
    except Exception:
        pass
    stale = [job_id for job_id, job in _JOBS.items() if now - float(job.get("updated_at", now)) > _JOB_TTL_SECONDS]
    for job_id in stale:
        _JOBS.pop(job_id, None)
    while len(_JOBS) > _MAX_JOBS:
        _JOBS.popitem(last=False)


def _create_job(kind: str, steps: list[str]) -> str:
    _cleanup_jobs()
    job_id = uuid.uuid4().hex
    now = time.time()
    _JOBS[job_id] = {
        "job_id": job_id,
        "kind": kind,
        "status": "queued",
        "steps": [{"name": name, "status": "pending", "summary": "", "elapsed_ms": 0} for name in steps],
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    _persist_job(_JOBS[job_id])
    return job_id


def _persist_job(job: dict[str, Any]) -> None:
    try:
        get_runtime_store().upsert_job(job)
    except Exception:
        pass


def get_job_snapshot(job_id: str) -> dict[str, Any] | None:
    job = _JOBS.get(job_id)
    if job:
        return job
    return get_runtime_store().get_job(job_id)


def _set_step(job: dict[str, Any], index: int, status: str, summary: str = "") -> None:
    if 0 <= index < len(job["steps"]):
        step = job["steps"][index]
        step["status"] = status
        step["summary"] = summary
        step["elapsed_ms"] = int((time.time() - job["created_at"]) * 1000)
    job["updated_at"] = time.time()
    _persist_job(job)


def _complete(job: dict[str, Any], result: dict[str, Any]) -> None:
    for index, step in enumerate(job["steps"]):
        if step["status"] in {"pending", "running"}:
            _set_step(job, index, "completed", step.get("summary") or "done")
    job["status"] = "completed"
    job["result"] = result
    job["updated_at"] = time.time()
    _persist_job(job)


def _cancel(job: dict[str, Any]) -> None:
    job["status"] = "cancelled"
    for step in job["steps"]:
        if step["status"] in {"pending", "running"}:
            step["status"] = "cancelled"
            step["summary"] = step.get("summary") or "cancelled"
            step["elapsed_ms"] = int((time.time() - job["created_at"]) * 1000)
    job["updated_at"] = time.time()
    _persist_job(job)


def _fail(job: dict[str, Any], exc: BaseException) -> None:
    message = f"{type(exc).__name__}: {exc}"
    for index, step in enumerate(job["steps"]):
        if step["status"] == "running":
            _set_step(job, index, "failed", message)
            break
    job["status"] = "failed"
    job["error"] = message[:500]
    job["updated_at"] = time.time()
    _persist_job(job)


def _run_forecast_job(job_id: str, req: ForecastRequestIn) -> None:
    job = _JOBS[job_id]
    try:
        if job.get("status") == "cancelled":
            return
        job["status"] = "running"
        _set_step(job, 0, "running", "validating request")
        internal_req = ForecastRequest.from_pydantic(req)
        _set_step(job, 0, "completed", "request accepted")
        _set_step(job, 1, "running", "running Kronos forecast")
        result = forecast_from_request(internal_req)
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error", "forecast failed")))
        _set_step(job, 1, "completed", "forecast complete")
        _complete(job, result)
    except BaseException as exc:
        _fail(job, exc)


def _run_agent_job(job_id: str, req: AgentAnalyzeRequest) -> None:
    job = _JOBS[job_id]
    try:
        from kronos_fincept.agent import analyze_investment_question

        if job.get("status") == "cancelled":
            return
        job["status"] = "running"
        _set_step(job, 0, "running", "understanding question")
        _set_step(job, 0, "completed", "question accepted")
        _set_step(job, 1, "running", "running analysis agent")
        result = analyze_investment_question(
            req.question,
            symbol=req.symbol,
            market=req.market,
            context=req.context,
            dry_run=req.dry_run,
        ).to_dict()
        _set_step(job, 1, "completed", "analysis complete")
        _complete(job, result)
    except BaseException as exc:
        _fail(job, exc)


def _run_batch_job(job_id: str, req: BatchJobRequest) -> None:
    job = _JOBS[job_id]
    try:
        if job.get("status") == "cancelled":
            return
        job["status"] = "running"
        progress = {"total": len(req.symbols), "completed": 0, "success": 0, "failed": 0, "running": []}
        failures: list[dict[str, Any]] = []
        assets: list[BatchForecastItemIn] = []

        _set_step(job, 0, "running", "fetching market data")
        for symbol in req.symbols:
            if job.get("status") == "cancelled":
                return
            progress["running"] = [symbol]
            try:
                rows = fetch_market_rows_for_batch(symbol, req.market, req.start_date, req.end_date, req.adjust)
                if not rows:
                    raise ValueError("No data")
                assets.append(BatchForecastItemIn(symbol=symbol, rows=rows[-1024:], model_id=req.model_id))
                progress["success"] += 1
            except Exception as exc:
                progress["failed"] += 1
                failures.append({"symbol": symbol, "stage": "data", "message": str(exc), "requestId": None, "retryable": True})
            finally:
                progress["completed"] += 1
                progress["running"] = []
        _set_step(job, 0, "completed", f"fetched {len(assets)} assets")

        if not assets:
            _set_step(job, 1, "cancelled", "no forecastable assets")
            _complete(job, {"ok": True, "rankings": [], "failures": failures, "progress": progress})
            return

        _set_step(job, 1, "running", "running batch forecast")
        batch_req = BatchForecastRequestIn(assets=assets[:20], pred_len=req.pred_len, dry_run=req.dry_run)
        forecast_requests = [_item_to_forecast_request(item, batch_req.pred_len, batch_req.dry_run) for item in batch_req.assets]
        signals = batch_forecast_from_requests(forecast_requests)
        rankings = [
            {
                "rank": sig.rank,
                "symbol": sig.symbol,
                "market": req.market,
                "last_close": sig.last_close,
                "predicted_close": sig.predicted_close,
                "predicted_return": sig.predicted_return,
                "elapsed_ms": sig.elapsed_ms,
            }
            for sig in signals
        ]
        _set_step(job, 1, "completed", f"ranked {len(rankings)} assets")

        _set_step(job, 2, "running", "building response")
        result = {
            "ok": True,
            "rankings": rankings,
            "failures": failures,
            "progress": {
                "total": len(req.symbols),
                "completed": len(req.symbols),
                "success": len(rankings),
                "failed": len(failures),
                "running": [],
            },
        }
        _set_step(job, 2, "completed", "done")
        _complete(job, result)
    except BaseException as exc:
        _fail(job, exc)


async def _run_backtest_job(job_id: str, req: BacktestRequestIn) -> None:
    job = _JOBS[job_id]
    try:
        if job.get("status") == "cancelled":
            return
        from kronos_fincept.api.routes.backtest import backtest_ranking

        job["status"] = "running"
        _set_step(job, 0, "running", "fetching aligned OHLCV data")
        _set_step(job, 0, "completed", "request accepted")
        _set_step(job, 1, "running", "running ranking strategy backtest")
        result = await backtest_ranking(req)
        _set_step(job, 1, "completed", "backtest complete")
        _set_step(job, 2, "running", "serializing metrics")
        _complete(job, result.model_dump())
    except BaseException as exc:
        _fail(job, exc)


@router.get("", response_model=JobHistoryResponse)
async def list_jobs(limit: int = 50, status: str | None = None, kind: str | None = None) -> JobHistoryResponse:
    _cleanup_jobs()
    merged: dict[str, dict[str, Any]] = {job["job_id"]: job for job in get_runtime_store().list_jobs(limit=limit, status=status, kind=kind)}
    for job_id, job in _JOBS.items():
        if (not status or job.get("status") == status) and (not kind or job.get("kind") == kind):
            merged[job_id] = job
    jobs = sorted(merged.values(), key=lambda item: float(item.get("updated_at", 0)), reverse=True)[: max(1, min(int(limit), 200))]
    return JobHistoryResponse(jobs=[JobStatusResponse(**job) for job in jobs], total=len(jobs))


@router.post("/forecast", response_model=JobSubmitResponse)
async def submit_forecast_job(req: ForecastRequestIn, background_tasks: BackgroundTasks) -> JobSubmitResponse:
    job_id = _create_job("forecast", ["校验请求", "Kronos 预测"])
    background_tasks.add_task(_run_forecast_job, job_id, req)
    return JobSubmitResponse(job_id=job_id, status="queued")


@router.post("/analyze", response_model=JobSubmitResponse)
async def submit_analyze_job(req: AgentAnalyzeRequest, background_tasks: BackgroundTasks) -> JobSubmitResponse:
    job_id = _create_job("analyze", ["理解问题", "AI 分析"])
    background_tasks.add_task(_run_agent_job, job_id, req)
    return JobSubmitResponse(job_id=job_id, status="queued")


@router.post("/batch", response_model=JobSubmitResponse)
async def submit_batch_job(req: BatchJobRequest, background_tasks: BackgroundTasks) -> JobSubmitResponse:
    job_id = _create_job("batch", ["行情数据", "批量预测", "结果整理"])
    if req.start_immediately:
        background_tasks.add_task(_run_batch_job, job_id, req)
    return JobSubmitResponse(job_id=job_id, status="queued")


@router.post("/backtest", response_model=JobSubmitResponse)
async def submit_backtest_job(req: BacktestJobRequest, background_tasks: BackgroundTasks) -> JobSubmitResponse:
    job_id = _create_job("backtest", ["行情数据", "回测执行", "指标汇总"])
    if req.start_immediately:
        payload = BacktestRequestIn(**req.model_dump(exclude={"start_immediately"}))
        background_tasks.add_task(_run_backtest_job, job_id, payload)
    return JobSubmitResponse(job_id=job_id, status="queued")


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str) -> JobStatusResponse:
    _cleanup_jobs()
    job = get_job_snapshot(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    _JOBS[job_id] = job
    return JobStatusResponse(**job)


@router.post("/{job_id}/cancel", response_model=JobCancelResponse)
async def cancel_job(job_id: str) -> JobCancelResponse:
    _cleanup_jobs()
    job = get_job_snapshot(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    _JOBS[job_id] = job
    if job["status"] in {"completed", "failed", "cancelled"}:
        return JobCancelResponse(job_id=job_id, status=job["status"])
    _cancel(job)
    return JobCancelResponse(job_id=job_id, status="cancelled")


def clear_jobs() -> None:
    _JOBS.clear()
