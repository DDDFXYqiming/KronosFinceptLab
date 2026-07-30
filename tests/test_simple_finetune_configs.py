from __future__ import annotations

from pathlib import Path

import yaml


CONFIG_DIR = (
    Path(__file__).resolve().parents[1]
    / "external"
    / "Kronos"
    / "finetune_csv"
    / "configs"
)


def test_simple_cycle_is_exactly_three_frozen_one_epoch_experiments():
    paths = [CONFIG_DIR / f"config_simple_m{index}.yaml" for index in range(1, 4)]
    configs = [yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths]

    assert [config["training"]["predictor_learning_rate"] for config in configs] == [
        0.000001,
        0.000005,
        0.000005,
    ]
    assert [config["training"]["sampling_strategy"] for config in configs] == [
        "window_uniform",
        "window_uniform",
        "market_stock_balanced",
    ]
    for index, config in enumerate(configs, start=1):
        assert config["model_paths"]["pretrained_predictor"] == "NeoQuasar/Kronos-small"
        assert config["model_paths"]["finetuned_tokenizer"] == "NeoQuasar/Kronos-Tokenizer-base"
        assert config["training"]["basemodel_epochs"] == 1
        assert config["training"]["seed"] == 42
        assert config["data"]["lookback_window"] == 90
        assert config["data"]["predict_window"] == 5
        assert config["data"]["split_mode"] == "calendar"
        assert config["data"]["data_path"] == "clean_v5_compact"
        assert config["data"]["train_start"] == "2022-01-01"
        assert config["data"]["train_end"] == "2025-12-31"
        assert config["data"]["validation_start"] == "2026-01-01"
        assert config["data"]["validation_end"] == "2026-03-31"
        assert config["data"]["diagnostic_start"] == "2026-04-01"
        assert config["data"]["diagnostic_end"] == "2026-07-31"
        assert config["data"]["strict_oos_start"] == "2026-08-01"
        assert config["data"]["embargo_bars"] == 5
        assert config["model_paths"]["base_path"] == f"finetuned_compact_m{index}"
        assert config["experiment"]["train_tokenizer"] is False
