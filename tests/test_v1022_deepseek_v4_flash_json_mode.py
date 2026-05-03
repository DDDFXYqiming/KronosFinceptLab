def test_v1022_deepseek_v4_flash_uses_non_thinking_json_mode():
    from kronos_fincept import agent

    options = agent._deepseek_structured_json_options(
        temperature=0.2,
        max_tokens=1800,
        model="deepseek-v4-flash",
    )

    assert options["response_format"] == {"type": "json_object"}
    assert options["thinking"] == {"type": "disabled"}
    assert options["temperature"] == 0.2
    assert options["max_tokens"] == 1800


def test_v1022_deepseek_legacy_model_keeps_json_mode_without_thinking():
    from kronos_fincept import agent

    options = agent._deepseek_structured_json_options(
        temperature=0,
        max_tokens=900,
        model="deepseek-chat",
    )

    assert options["response_format"] == {"type": "json_object"}
    assert "thinking" not in options


def test_v1022_deepseek_empty_content_does_not_raise():
    from kronos_fincept.agent import _deepseek_finish_reason, _deepseek_message_content, _extract_json_object

    payload = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {
                    "content": None,
                    "reasoning_content": None,
                },
            }
        ]
    }

    assert _deepseek_message_content(payload) is None
    assert _deepseek_finish_reason(payload) == "length"
    assert _extract_json_object(None) is None


def test_v1022_deepseek_message_content_extracts_json_string():
    from kronos_fincept.agent import _deepseek_message_content

    payload = {"choices": [{"message": {"content": '{"conclusion": "ok"}'}}]}

    assert _deepseek_message_content(payload) == '{"conclusion": "ok"}'


def test_v1022_deepseek_report_prompt_escapes_json_example(monkeypatch):
    from types import SimpleNamespace

    import requests

    from kronos_fincept import agent

    captured: dict[str, object] = {}

    fake_settings = SimpleNamespace(
        llm=SimpleNamespace(
            deepseek=SimpleNamespace(
                api_key="sk-test",
                base_url="https://api.deepseek.com",
                model="deepseek-v4-flash",
                is_configured=True,
            )
        )
    )

    class FakeResponse:
        status_code = 200
        text = '{"choices":[]}'

        def json(self):
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": (
                                '{"conclusion":"ok","short_term_prediction":"ok",'
                                '"technical":"ok","fundamentals":"ok","risk":"ok",'
                                '"uncertainties":"ok","recommendation":"持有",'
                                '"confidence":0.7,"risk_level":"中","disclaimer":"仅供研究"}'
                            )
                        },
                    }
                ]
            }

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr(agent, "settings", fake_settings)
    monkeypatch.setattr(requests, "post", fake_post)

    report = agent._call_deepseek_report("帮我看看东方财富现在能不能买", {"asset_contexts": []})

    request_json = captured["json"]
    assert isinstance(request_json, dict)
    system_prompt = request_json["messages"][0]["content"]
    assert '"symbol": "600036"' in system_prompt
    assert report is not None
    assert report["conclusion"] == "ok"
