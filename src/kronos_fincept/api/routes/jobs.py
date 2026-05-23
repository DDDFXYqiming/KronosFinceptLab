"""In-process job endpoints for slow forecast and analysis operations."""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from kronos_fincept.api.models import ForecastRequestIn
from kronos_fincept.api.routes.ai_analyze import AgentAnalyzeRequest
from kronos_fincept.schemas import ForecastRequest
from kronos_fincept.service import forecast_from_request

router = APIRouter(prefix="/jobs", tags=["jobs"])

_MAX_JOBS = 100
_JOB_TTL_SECONDS = 3600
_JOBS: "OrderedDict[str, dict[str, Any]]" = OrderedDict()


class JobSubmitResponse(BaseModel):
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


def _cleanup_jobs(now: float | None = None) -> None:
    now = now or time.time()
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
    return job_id


def _set_step(job: dict[str, Any], index: int, status: str, summary: str = "") -> None:
    if 0 <= index < len(job["steps"]):
        step = job["steps"][index]
        step["status"] = status
        step["summary"] = summary
        step["elapsed_ms"] = int((time.time() - job["created_at"]) * 1000)
    job["updated_at"] = time.time()


def _complete(job: dict[str, Any], result: dict[str, Any]) -> None:
    for index, step in enumerate(job["steps"]):
        if step["status"] in {"pending", "running"}:
            _set_step(job, index, "completed", step.get("summary") or "done")
    job["status"] = "completed"
    job["result"] = result
    job["updated_at"] = time.time()


def _fail(job: dict[str, Any], exc: BaseException) -> None:
    message = f"{type(exc).__name__}: {exc}"
    for index, step in enumerate(job["steps"]):
        if step["status"] == "running":
            _set_step(job, index, "failed", message)
            break
    job["status"] = "failed"
    job["error"] = message[:500]
    job["updated_at"] = time.time()


def _run_forecast_job(job_id: str, req: ForecastRequestIn) -> None:
    job = _JOBS[job_id]
    try:
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


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(job_id: str) -> JobStatusResponse:
    _cleanup_jobs()
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatusResponse(**job)


def clear_jobs() -> None:
    _JOBS.clear()
