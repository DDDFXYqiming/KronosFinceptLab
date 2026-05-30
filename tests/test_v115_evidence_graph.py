"""v11.5 Evidence Graph Agent regression tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from kronos_fincept.api.app import app


def test_v115_agent_analysis_returns_evidence_pack_and_cited_claims():
    client = TestClient(app)
    resp = client.post("/api/v1/analyze/agent", json={
        "question": "帮我分析招商银行现在能不能买",
        "symbol": "600036",
        "market": "cn",
        "dry_run": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    evidence_pack = data["evidence_pack"]
    assert evidence_pack["version"] == "v11.5"
    assert evidence_pack["items"]
    assert {item["category"] for item in evidence_pack["items"]} >= {"price", "forecast"}
    assert all(item["id"] for item in evidence_pack["items"])
    assert data["cited_claims"]
    assert all(claim["evidence_ids"] for claim in data["cited_claims"])
    evidence_ids = {item["id"] for item in evidence_pack["items"]}
    assert set(data["cited_claims"][0]["evidence_ids"]).issubset(evidence_ids)
    breakdown = data["confidence_breakdown"]
    assert set(breakdown) >= {"data_coverage", "forecast_support", "risk_support", "final"}
    assert breakdown["final"] == data["confidence"]


def test_v115_frontend_exposes_evidence_graph_viewer_contract():
    page = Path("web/src/app/analysis/page.tsx").read_text(encoding="utf-8")
    types = Path("web/src/types/api.ts").read_text(encoding="utf-8")

    assert "Evidence Graph" in page
    assert "evidence_pack" in page
    assert "cited_claims" in page
    assert "confidence_breakdown" in page
    assert "EvidencePack" in types
    assert "CitedClaim" in types
