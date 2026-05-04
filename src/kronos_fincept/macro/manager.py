"""Macro provider orchestration and graceful degradation."""

from __future__ import annotations

import concurrent.futures
import time
from typing import Iterable

from kronos_fincept.macro.providers import MacroProvider, create_default_providers
from kronos_fincept.macro.schemas import MacroGatherResult, MacroProviderResult, MacroQuery, MacroSignal


class MacroDataManager:
    """Run macro providers concurrently and normalize partial results."""

    def __init__(
        self,
        providers: Iterable[MacroProvider] | None = None,
        *,
        cache_ttl_seconds: int = 300,
        timeout_seconds: float = 20.0,
        per_provider_timeout_seconds: float = 10.0,
        failure_threshold: int = 3,
        failure_cooldown_seconds: int = 300,
        max_workers: int | None = None,
    ) -> None:
        self.providers = {provider.provider_id: provider for provider in (providers or create_default_providers())}
        self.cache_ttl_seconds = max(0, cache_ttl_seconds)
        self.timeout_seconds = max(0.1, timeout_seconds)
        self.per_provider_timeout_seconds = max(0.1, per_provider_timeout_seconds)
        self.failure_threshold = max(1, failure_threshold)
        self.failure_cooldown_seconds = max(1, failure_cooldown_seconds)
        self.max_workers = max_workers
        self._cache: dict[str, tuple[float, MacroProviderResult]] = {}
        self._failure_counts: dict[str, int] = {}
        self._suspended_until: dict[str, float] = {}

    def describe_providers(self) -> list[dict]:
        return [provider.describe().to_dict() for provider in self.providers.values()]

    def gather(
        self,
        query: str | MacroQuery | None = None,
        *,
        provider_ids: Iterable[str] | None = None,
    ) -> MacroGatherResult:
        macro_query = query if isinstance(query, MacroQuery) else MacroQuery(question=query or "")
        selected = self._select_providers(provider_ids)
        if not selected:
            return MacroGatherResult(signals=[], provider_results={})

        results: dict[str, MacroProviderResult] = {}
        tasks: dict[concurrent.futures.Future[MacroProviderResult], str] = {}
        worker_count = self.max_workers or min(len(selected), 8)

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=worker_count)
        try:
            for provider in selected:
                suspended_result = self._suspended_result(provider.provider_id)
                if suspended_result is not None:
                    results[provider.provider_id] = suspended_result
                    continue
                cached = self._get_cached(provider.provider_id, macro_query)
                if cached is not None:
                    results[provider.provider_id] = cached
                    continue
                tasks[executor.submit(self._run_provider, provider, macro_query)] = provider.provider_id

            done, not_done = concurrent.futures.wait(
                tasks.keys(),
                timeout=self.timeout_seconds,
                return_when=concurrent.futures.ALL_COMPLETED,
            )

            for future in done:
                provider_id = tasks[future]
                try:
                    result = future.result(timeout=0)
                except Exception as exc:
                    result = self._failed_result(provider_id, exc)
                results[provider_id] = result
                self._record_provider_result(provider_id, result)
                self._set_cached(provider_id, macro_query, result)

            for future in not_done:
                provider_id = tasks[future]
                future.cancel()
                result = MacroProviderResult(
                    provider_id=provider_id,
                    status="failed",
                    signals=[],
                    error=f"provider timed out after {self.timeout_seconds:g}s",
                )
                results[provider_id] = result
                self._record_provider_result(provider_id, result)
                self._set_cached(provider_id, macro_query, result)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        signals: list[MacroSignal] = []
        for provider_id in [provider.provider_id for provider in selected]:
            signals.extend(results.get(provider_id, MacroProviderResult(provider_id, "empty")).signals)
        return MacroGatherResult(signals=signals, provider_results=results)

    def _select_providers(self, provider_ids: Iterable[str] | None) -> list[MacroProvider]:
        if provider_ids is None:
            return list(self.providers.values())
        return [self.providers[item] for item in provider_ids if item in self.providers]

    def _run_provider(self, provider: MacroProvider, query: MacroQuery) -> MacroProviderResult:
        started = time.perf_counter()
        single = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = single.submit(provider.fetch_signals, query)
            try:
                signals = future.result(timeout=self.per_provider_timeout_seconds)
            except concurrent.futures.TimeoutError:
                future.cancel()
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return MacroProviderResult(
                    provider_id=provider.provider_id,
                    status="failed",
                    signals=[],
                    elapsed_ms=elapsed_ms,
                    error=f"provider timed out after {self.per_provider_timeout_seconds:g}s",
                )
        finally:
            single.shutdown(wait=False, cancel_futures=True)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        status = "completed" if signals else "empty"
        return MacroProviderResult(provider_id=provider.provider_id, status=status, signals=signals, elapsed_ms=elapsed_ms)

    def _record_provider_result(self, provider_id: str, result: MacroProviderResult) -> None:
        if result.status != "failed":
            self._failure_counts.pop(provider_id, None)
            self._suspended_until.pop(provider_id, None)
            return
        failures = self._failure_counts.get(provider_id, 0) + 1
        self._failure_counts[provider_id] = failures
        if failures >= self.failure_threshold:
            self._suspended_until[provider_id] = time.time() + self.failure_cooldown_seconds
            self._failure_counts[provider_id] = 0

    def _suspended_result(self, provider_id: str) -> MacroProviderResult | None:
        resume_at = self._suspended_until.get(provider_id)
        if resume_at is None:
            return None
        remaining = int(max(0, resume_at - time.time()))
        if remaining <= 0:
            self._suspended_until.pop(provider_id, None)
            return None
        return MacroProviderResult(
            provider_id=provider_id,
            status="skipped",
            signals=[],
            error=f"provider suspended after repeated failures ({remaining}s remaining)",
        )

    def _failed_result(self, provider_id: str, exc: BaseException) -> MacroProviderResult:
        return MacroProviderResult(
            provider_id=provider_id,
            status="failed",
            signals=[],
            error=_short_error(exc),
        )

    def _cache_key(self, provider_id: str, query: MacroQuery) -> str:
        return f"{provider_id}|{query.cache_key()}"

    def _get_cached(self, provider_id: str, query: MacroQuery) -> MacroProviderResult | None:
        if self.cache_ttl_seconds <= 0:
            return None
        cache_key = self._cache_key(provider_id, query)
        cached = self._cache.get(cache_key)
        if cached is None:
            return None
        stored_at, result = cached
        if time.time() - stored_at > self.cache_ttl_seconds:
            self._cache.pop(cache_key, None)
            return None
        return result

    def _set_cached(self, provider_id: str, query: MacroQuery, result: MacroProviderResult) -> None:
        if self.cache_ttl_seconds <= 0:
            return
        self._cache[self._cache_key(provider_id, query)] = (time.time(), result)


def _short_error(exc: BaseException, *, limit: int = 180) -> str:
    message = " ".join((str(exc).strip() or type(exc).__name__).split())
    return message if len(message) <= limit else message[: limit - 3] + "..."
