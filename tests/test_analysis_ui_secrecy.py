from __future__ import annotations

from pathlib import Path


def test_analysis_page_does_not_render_internal_multi_asset_instruction():
    page = (
        Path(__file__).resolve().parents[1]
        / "web"
        / "src"
        / "app"
        / "analysis"
        / "page.tsx"
    ).read_text(encoding="utf-8")

    assert "多标的请求按标的拆分展示，顶部仅保留整体比较结论。" not in page
    assert "Multi-asset requests are split by asset below; the top keeps only the overall comparison." not in page
