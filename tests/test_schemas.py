from kronos_fincept.schemas import ForecastRequest, ForecastRow, build_error_response


def test_forecast_request_fills_optional_volume_and_amount():
    request = ForecastRequest.from_dict(
        {
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "pred_len": 2,
            "rows": [
                {
                    "timestamp": "2026-04-29T00:00:00Z",
                    "open": 100,
                    "high": 110,
                    "low": 90,
                    "close": 105,
                }
            ],
        }
    )

    assert request.symbol == "BTC/USDT"
    assert request.model_id == "NeoQuasar/Kronos-small"
    assert request.tokenizer_id == "NeoQuasar/Kronos-Tokenizer-base"
    assert request.rows[0].volume == 0.0
    assert request.rows[0].amount == 0.0


def test_forecast_row_rejects_invalid_ohlc():
    try:
        ForecastRow.from_dict(
            {
                "timestamp": "2026-04-29T00:00:00Z",
                "open": 100,
                "high": 99,
                "low": 90,
                "close": 105,
            }
        )
    except ValueError as exc:
        assert "high" in str(exc)
    else:
        raise AssertionError("invalid OHLC row should fail")


def test_build_error_response_is_stable_json_contract():
    response = build_error_response("boom", symbol="BTC/USDT")

    assert response == {"ok": False, "symbol": "BTC/USDT", "error": "boom"}
