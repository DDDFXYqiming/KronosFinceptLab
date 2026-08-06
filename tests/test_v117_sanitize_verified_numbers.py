"""Verified-number sanitizer: whitelist expansion + normalized matching."""

from __future__ import annotations

from kronos_fincept import agent


def _sample_asset() -> dict:
    return {
        "symbol": "600036",
        "market": "cn",
        "name": "招商银行",
        "asset_class": "equity",
        "market_data": {
            "current_price": 38.97,
            "data_points": 363,
            "high_52w": 42.94,
            "low_52w": 34.34,
            "price_change_1d": 0.08,
            "price_change_1w": -1.64,
            "rows": [{"timestamp": "2026-08-06T00:00:00Z", "close": 38.97}],
        },
        "financial_data": {"pe": 6.52, "pb": 0.87, "roe": 0.118, "period": "2025-12-31"},
        "methodology": {
            "rules": [
                {
                    "id": "fibonacci_levels",
                    "name": "斐波那契回撤位",
                    "status": "ok",
                    "detail": "0.618=37.80，0.5=38.87，0.382=39.93；现价位于0.618上方。",
                    "evidence": {"f_618": 37.8, "f_50": 38.87, "f_382": 39.93},
                }
            ],
            "pr": {
                "status": "ok",
                "formula": "F1: PE/(ROE×100)",
                "pr": 0.552542,
                "band": "6折分批/轻仓试探区",
                "detail": "市赚率PR=0.552，处于6折分批区。",
            },
        },
        "technical_indicators": {"rsi_14": {"values": [54.0]}},
        "kronos_prediction": {
            "model": "NeoQuasar/Kronos-small",
            "prediction_days": 5,
            "forecast": [{"timestamp": "2026-08-07", "close": 38.95}],
            "probabilistic": {"up_probability": 0.25},
        },
        "risk_metrics": {"volatility": 0.1791, "var_95": 0.0169, "max_drawdown": 0.2124},
    }


def test_verified_numbers_preserved_verbatim():
    contexts = [_sample_asset()]
    report = {
        "macro_signals": [
            {
                "source": "china_macro_akshare",
                "signal_type": "pmi",
                "value": 49.7,
                "interpretation": "中国官方制造业PMI为49.7，低于荣枯线。",
            }
        ]
    }
    text = "现价38.97元位于斐波那契37.80回撤位附近；PR=0.55，处于6折分批区；上行概率25%；PMI 49.7。"
    out = agent._sanitize_unverified_numbers(text, contexts, report=report)
    assert out == text
    assert "待验证" not in out
    assert "提示：" not in out


def test_percent_and_fraction_normalization():
    contexts = [_sample_asset()]
    text = "上行概率仅25%，波动率17.91%。"
    out = agent._sanitize_unverified_numbers(text, contexts)
    assert "待验证" not in out
    assert "提示：" not in out


def test_unverified_external_number_still_flagged_without_hint():
    contexts = [{"symbol": "TEST", "market": "cn", "name": "测试标的"}]
    text = "外部网页称库存123万吨。"
    out = agent._sanitize_unverified_numbers(text, contexts)
    assert "待验证" in out
    assert "提示：" not in out


def test_year_and_date_like_tokens_preserved():
    contexts = [{"symbol": "TEST", "market": "cn", "name": "测试标的"}]
    text = "2025年年报显示2026年展望中性；当前为2026-08-07。"
    out = agent._sanitize_unverified_numbers(text, contexts)
    assert "待验证" not in out
    assert "提示：" not in out


def test_thousand_separator_tokens_match():
    contexts = [
        {
            "symbol": "TEST",
            "market": "cn",
            "name": "测试标的",
            "financial_data": {"market_cap": 1234567.0},
        }
    ]
    text = "总市值约1,234,567万元。"
    out = agent._sanitize_unverified_numbers(text, contexts)
    assert "待验证" not in out
