from __future__ import annotations

import inspect


def test_kronos_top_p_filtering_uses_functional_tensor_updates():
    """DirectML cannot reliably execute the upstream in-place bool slice write."""
    from kronos_fincept import predictor

    source = inspect.getsource(predictor._dml_safe_top_k_top_p_filtering)

    assert "sorted_indices_to_remove[..., 1:] =" not in source
    assert "masked_fill" in source
