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
