from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_v92_batch_page_uses_limited_concurrency_and_backend_batch():
    page = read("web/src/app/batch/page.tsx")

    assert "const BATCH_CONCURRENCY = 4" in page
    assert "runWithConcurrency" in page
    assert "Promise.allSettled" in page
    assert "api.batch(" in page
    assert "api.forecast(" not in page
    assert "queryKeys.batch" in page
    assert "queryClient.getQueryData<BatchRunSnapshot>" in page
    assert "queryClient.fetchQuery" in page


def test_v92_batch_page_supports_abort_and_removes_cancelled_cache():
    page = read("web/src/app/batch/page.tsx")

    assert "AbortController" in page
    assert "activeAbortRef" in page
    assert "handleCancel" in page
    assert "取消任务" in page
    assert "abortController.signal" in page
    assert "removeQueries({ queryKey: key, exact: true })" in page
    assert "任务已取消" in page


def test_v92_batch_page_tracks_progress_and_partial_failures():
    page = read("web/src/app/batch/page.tsx")

    for token in [
        "BatchProgress",
        "total",
        "completed",
        "success",
        "failed",
        "skipped",
        "running",
        "kronos-batch-failures",
        "BatchFailure",
        "失败项",
        "request_id=",
        "重试",
        "retryable",
    ]:
        assert token in page


def test_v92_version_labels_are_updated():
    assert "Version: v9.3" in read("README.md")
    assert "v9.3" in read("web/src/components/layout/Sidebar.tsx")
