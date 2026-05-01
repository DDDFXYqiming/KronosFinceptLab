from __future__ import annotations

from datetime import datetime

from kronos_fincept.data_sources import DataSourceManager


def test_memory_cache_evicts_least_recently_used(tmp_path):
    manager = DataSourceManager(cache_dir=str(tmp_path))
    manager.memory_cache_max_size = 2

    manager._save_to_cache("first", {"value": 1}, ttl=60)
    manager._save_to_cache("second", {"value": 2}, ttl=60)
    assert manager._get_from_cache("first") == {"value": 1}

    manager._save_to_cache("third", {"value": 3}, ttl=60)

    assert list(manager.memory_cache.keys()) == ["first", "third"]
    assert manager._get_from_cache("second") is not None
    assert list(manager.memory_cache.keys()) == ["third", "second"]


def test_memory_cache_removes_expired_entries(tmp_path):
    manager = DataSourceManager(cache_dir=str(tmp_path))
    manager._set_memory_cache(
        "expired",
        {
            "data": {"value": 1},
            "expire_at": datetime.now().timestamp() - 1,
            "created_at": datetime.now().isoformat(),
        },
    )

    assert manager._get_from_cache("expired") is None
    assert "expired" not in manager.memory_cache
