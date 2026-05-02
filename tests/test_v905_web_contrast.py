from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_analysis_report_uses_design_tokens_for_light_card_text():
    page = read("web/src/app/analysis/page.tsx")

    assert 'text-sm font-semibold text-foreground mb-2' in page
    assert 'text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap' in page
    assert 'border-b border-border last:border-b-0' in page
    assert 'text-muted-foreground leading-relaxed' in page
    assert 'text-sm text-foreground font-mono' in page


def test_analysis_light_cards_do_not_use_low_contrast_gray_body_text():
    page = read("web/src/app/analysis/page.tsx")

    low_contrast_patterns = [
        "text-gray-200",
        "text-gray-300",
        "text-gray-400",
        "text-gray-500",
        "border-gray-800",
        "hover:bg-surface-overlay",
    ]
    for pattern in low_contrast_patterns:
        assert pattern not in page

    # Dark input remains intentionally inverted per the existing design.
    assert "bg-surface-overlay border border-gray-700 rounded-lg text-white" in page


def test_v905_version_labels_are_updated():
    assert "Version: v9.0.5" in read("README.md")
    assert "v9.0.5" in read("web/src/components/layout/Sidebar.tsx")
