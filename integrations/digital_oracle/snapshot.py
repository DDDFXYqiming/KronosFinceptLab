"""
Snapshot/Replay testing infrastructure for KFL + Digital Oracle.

Wraps DO's RecordingHttpClient / ReplayHttpClient as pytest fixtures,
enabling offline backtesting and regression testing without network.

Usage (pytest conftest.py / test files):
    from integrations.digital_oracle.snapshot import SnapshotContext

    # Record mode — one-time: capture real API responses
    with SnapshotContext.record("tests/snapshots") as ctx:
        provider = ctx.provider(PolymarketProvider)
        signals = ctx.collect(provider.fetch_signals)  # HTTP calls recorded

    # Replay mode — CI / offline: read from disk, no network
    with SnapshotContext.replay("tests/snapshots") as ctx:
        provider = ctx.provider(PolymarketProvider)
        signals = ctx.collect(provider.fetch_signals)  # uses cached data

    # As pytest fixture:
    @pytest.fixture
    def snapshot_ctx(tmp_path):
        with SnapshotContext.record(tmp_path / "snapshots") as ctx:
            yield ctx
"""

from __future__ import annotations

import contextlib
import enum
from pathlib import Path
from typing import Any, cast

from digital_oracle.snapshots import (
    RecordingHttpClient,
    ReplayHttpClient,
    SnapshotMissError,
)

__all__ = [
    "SnapshotContext",
    "SnapshotMode",
    "SnapshotMissError",
    "record_snapshot",
    "replay_snapshot",
]


class SnapshotMode(str, enum.Enum):
    """Snapshot operation mode."""
    RECORD = "record"
    REPLAY = "replay"
    LIVE = "live"


class SnapshotContext:
    """Context manager for snapshot recording/replay.

    Usage:
        # Record
        with SnapshotContext.record("tests/snapshots") as ctx:
            p = ctx.provider(PolymarketProvider)
            ...

        # Replay
        with SnapshotContext.replay("tests/snapshots") as ctx:
            p = ctx.provider(PolymarketProvider)
            ...
    """

    def __init__(
        self,
        mode: SnapshotMode,
        snapshot_dir: str | Path,
    ) -> None:
        self.mode = mode
        self.snapshot_dir = Path(snapshot_dir)
        self._client: RecordingHttpClient | ReplayHttpClient | None = None

        if mode == SnapshotMode.RECORD:
            self._client = RecordingHttpClient(self.snapshot_dir)
        elif mode == SnapshotMode.REPLAY:
            self._client = ReplayHttpClient(self.snapshot_dir)

    # ------------------------------------------------------------------
    # Factory constructors
    # ------------------------------------------------------------------

    @classmethod
    def record(cls, snapshot_dir: str | Path) -> "SnapshotContext":
        """Enter recording mode: HTTP calls are forwarded to real API
        and *also* saved to disk for later replay."""
        return cls(SnapshotMode.RECORD, snapshot_dir)

    @classmethod
    def replay(cls, snapshot_dir: str | Path) -> "SnapshotContext":
        """Enter replay mode: HTTP calls are served from cached snapshots.
        Raises SnapshotMissError if a request has no saved response."""
        return cls(SnapshotMode.REPLAY, snapshot_dir)

    @classmethod
    def live(cls) -> "SnapshotContext":
        """Pass-through mode: no snapshotting, normal HTTP."""
        return cls(SnapshotMode.LIVE, ".")

    # ------------------------------------------------------------------
    # Provider helpers
    # ------------------------------------------------------------------

    def provider(self, provider_cls: type, *args: Any, **kwargs: Any) -> Any:
        """Create a DO provider with snapshot HTTP client injected.

        Works for any DO provider whose constructor accepts an
        ``http_client`` keyword argument (Polymarket, Kalshi, Deribit,
        CMEFedWatch, FearGreed, etc.).  Duck-typing means both
        RecordingHttpClient and ReplayHttpClient satisfy the
        JsonHttpClient Protocol.

        For providers without an http_client parameter (e.g. YFinance
        with its OptionsFetcher) this still works as a pass-through;
        the provider will use its default HTTP backend.
        """
        if self._client is not None:
            kwargs.setdefault("http_client", self._client)
        return provider_cls(*args, **kwargs)

    def wrap(self, existing_provider: Any) -> Any:
        """Monkey-patch an *already-created* DO provider to use
        the snapshot client.

        Only providers storing their client in ``.http_client`` are
        affected (Polymarket, Kalshi, Deribit, CMEFedWatch, etc.).
        """
        if self._client is not None and hasattr(existing_provider, "http_client"):
            existing_provider.http_client = self._client
        return existing_provider

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "SnapshotContext":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """Release resources (no-op for snapshot clients)."""
        pass


# ------------------------------------------------------------------
# Convenience fixture factories  (ready for conftest.py)
# ------------------------------------------------------------------

@contextlib.contextmanager
def record_snapshot(
    snapshot_dir: str | Path,
) -> Any:
    """Yield a recording SnapshotContext.

    Conftest usage::

        @pytest.fixture
        def snapshot(request, tmp_path):
            with record_snapshot(tmp_path / "snapshots") as ctx:
                yield ctx

    Parallel-safe (each test gets its own tmpdir).
    """
    with SnapshotContext.record(snapshot_dir) as ctx:
        yield ctx


@contextlib.contextmanager
def replay_snapshot(
    snapshot_dir: str | Path,
) -> Any:
    """Yield a replay SnapshotContext.

    Conftest usage::

        @pytest.fixture(scope="session")
        def snapshot():
            with replay_snapshot("tests/fixtures/snapshots") as ctx:
                yield ctx

    Shared snapshot directory — session scope, read-only in CI.
    """
    with SnapshotContext.replay(snapshot_dir) as ctx:
        yield ctx
