from __future__ import annotations

from pathlib import Path

import yaml


CONFIG = (
    Path(__file__).resolve().parents[1]
    / "external"
    / "Kronos"
    / "finetune_csv"
    / "configs"
    / "config_largecap_l3_l2cont.yaml"
)


def test_l2_continuation_config_is_bounded_and_uses_l2_parent():
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    training = config["training"]
    data = config["data"]

    assert config["model_paths"]["pretrained_predictor"] == (
        "finetuned_largecap_l2_v3cont/basemodel/best_model"
    )
    assert config["model_paths"]["base_path"] == "finetuned_largecap_l3_l2cont"
    assert training["basemodel_epochs"] == 5
    assert training["early_stopping_enabled"] is True
    assert training["early_stopping_patience"] == 2
    assert training["early_stopping_min_delta"] == 0.001
    assert training["parent_validation_loss"] == 3.1394
    assert training["predictor_learning_rate"] == 0.000001
    assert training["batch_size"] == 32
    assert training["accumulation_steps"] == 4
    assert training["sampling_strategy"] == "market_stock_balanced"
    assert data["data_path"] == "clean_v6_largecap"
    assert data["train_start"] == "2022-01-01"
    assert data["train_end"] == "2025-12-31"
    assert data["validation_start"] == "2026-01-01"
    assert data["validation_end"] == "2026-03-31"
