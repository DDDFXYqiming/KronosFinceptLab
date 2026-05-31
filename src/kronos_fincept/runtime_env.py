"""Process-level runtime defaults for constrained local deployments."""

from __future__ import annotations

import os


LOW_MEMORY_ENV_DEFAULTS: dict[str, str] = {
    "OPENBLAS_NUM_THREADS": "1",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_MAX_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
    "TOKENIZERS_PARALLELISM": "false",
}


def apply_low_memory_defaults() -> None:
    """Apply thread caps before numerical libraries are imported.

    Set ``KRONOS_LOW_MEMORY_DEFAULTS=0`` to opt out when running on a machine
    where the extra BLAS/tokenizer parallelism is desired.
    """
    enabled = os.environ.get("KRONOS_LOW_MEMORY_DEFAULTS", "1").strip().lower()
    if enabled in {"0", "false", "no", "off"}:
        return
    for key, value in LOW_MEMORY_ENV_DEFAULTS.items():
        os.environ.setdefault(key, value)
