from __future__ import annotations

import os

from examples.run_simple_training import _TrainingLock


def test_training_lock_recovers_when_recorded_process_is_gone(tmp_path):
    lock_path = tmp_path / "training.lock"
    lock_path.write_text("999999999", encoding="utf-8")

    with _TrainingLock(lock_path):
        assert lock_path.read_text(encoding="utf-8") == str(os.getpid())

    assert not lock_path.exists()
