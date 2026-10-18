from paylane.transport import CallGate, safe_error


def test_gate_spaces_requests_and_honors_retry_after():
    now = [0.0]
    calls = []
    gate = CallGate(
        interval=1,
        concurrency=1,
        clock=lambda: now[0],
        sleep=lambda n: now.__setitem__(0, now[0] + n),
    )
    gate.call(lambda: calls.append(now[0]))
    gate.call(lambda: calls.append(now[0]))
    assert calls == [0, 1]
    gate.defer(5)
    gate.call(lambda: calls.append(now[0]))
    assert calls[-1] >= 6


def test_error_metadata_never_includes_exception_message():
    class Error(Exception):
        status_code = 429

    r = safe_error(Error("password is synthetic-secret"))
    assert r["status_code"] == 429 and "synthetic-secret" not in str(r)


def test_rate_limit_diagnostic_retains_only_known_source_not_provider_body():
    class Error(Exception):
        status_code = 429
        body = {
            "error": {
                "metadata": {
                    "limit_source": "upstream_provider_shared_pool",
                    "raw": "password is synthetic-secret",
                    "provider_name": "synthetic-secret",
                }
            }
        }

    result = safe_error(Error("synthetic-secret"))
    assert result["limit_source"] == "upstream_provider_shared_pool"
    assert "synthetic-secret" not in str(result)
    Error.body["error"]["metadata"]["limit_source"] = "synthetic-secret"
    assert "limit_source" not in safe_error(Error())
    Error.body["error"]["metadata"]["limit_source"] = ["untrusted"]
    assert "limit_source" not in safe_error(Error())


def test_integer_judge_requires_schema_without_unused_logprob_routing(monkeypatch):
    import json
    from types import SimpleNamespace
    from openai.types.chat import ChatCompletion
    from paylane.transport import make_judge

    judge = make_judge("test/model", "test-only")
    payloads = []

    def create(**kwargs):
        payloads.append(kwargs)
        fmt = kwargs.get("response_format", {})
        content = (
            '{"score":10,"reason":"Correct"}'
            if fmt.get("type") == "json_schema"
            else "not json"
        )
        return ChatCompletion.model_validate(
            {
                "id": "test",
                "object": "chat.completion",
                "created": 1,
                "model": "test/model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        )

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(judge, "load_model", lambda **kwargs: client)
    completion, cost = judge._generate_raw_response("Give a JSON score and reason")
    assert json.loads(completion.choices[0].message.content)["score"] == 10
    assert "logprobs" not in payloads[0] and "top_logprobs" not in payloads[0]
    assert set(payloads[0]["response_format"]["json_schema"]["schema"]["required"]) == {
        "score",
        "reason",
    }


@__import__("pytest").mark.parametrize("eventually_valid", [True, False])
def test_judge_contract_repair_is_bounded_and_retained(monkeypatch, eventually_valid):
    import pytest
    from types import SimpleNamespace
    from openai.types.chat import ChatCompletion
    import paylane.transport as t

    monkeypatch.setattr(t, "JUDGE_GATE", t.CallGate(interval=0))
    judge = t.make_judge("test/model", "test-only")
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        content = (
            '{"score":9,"reason":"Correct"}'
            if eventually_valid and len(calls) == 2
            else "not json"
        )
        return ChatCompletion.model_validate(
            {
                "id": "test",
                "object": "chat.completion",
                "created": 1,
                "model": "test/model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        )

    monkeypatch.setattr(
        judge,
        "load_model",
        lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    if eventually_valid:
        result, cost = judge._generate_raw_response("Grade the evidence")
        assert '"score":9' in result.choices[0].message.content
    else:
        with pytest.raises(ValueError, match="invalid_judge_output"):
            judge._generate_raw_response("Grade the evidence")
    assert len(calls) == 2
    assert sum(e.get("phase") == "validation" for e in judge.request_events) == (
        1 if eventually_valid else 2
    )


def test_judge_client_has_bounded_timeout_without_hidden_sdk_retries():
    from paylane.transport import make_judge

    client = make_judge("test/model", "test-only").load_model(async_mode=False)
    try:
        assert client.timeout == 20
        assert client.max_retries == 0
    finally:
        client.close()


def test_valid_judge_rating_without_usage_has_unknown_cost_not_a_retry(monkeypatch):
    from types import SimpleNamespace
    from openai.types.chat import ChatCompletion
    import paylane.transport as t

    monkeypatch.setattr(t, "JUDGE_GATE", t.CallGate(interval=0))
    judge = t.make_judge("test/model", "test-only")
    completion = ChatCompletion.model_validate(
        {
            "id": "test",
            "object": "chat.completion",
            "created": 1,
            "model": "test/model",
            "usage": None,
            "provider": "Nebius",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": '{"reason":"Correct","score":9}',
                    },
                }
            ],
        }
    )
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return completion

    monkeypatch.setattr(
        judge,
        "load_model",
        lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    result, cost = judge._generate_raw_response("Grade the reply")
    assert result.choices[0].message.content == '{"reason":"Correct","score":9}'
    assert cost is None and len(calls) == 1
    assert judge.request_events[0]["response_provider"] == "Nebius"


def test_empty_judge_choices_are_recorded_and_repaired_before_scoring(monkeypatch):
    from types import SimpleNamespace
    from openai.types.chat import ChatCompletion
    import paylane.transport as t

    monkeypatch.setattr(t, "JUDGE_GATE", t.CallGate(interval=0))
    judge = t.make_judge("test/model", "test-only")
    base = {
        "id": "test",
        "object": "chat.completion",
        "created": 1,
        "model": "test/model",
        "usage": None,
    }
    responses = [
        ChatCompletion.model_validate(base | {"choices": []}),
        ChatCompletion.model_validate(
            base
            | {
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"reason":"Correct","score":9}',
                        },
                    }
                ]
            }
        ),
    ]
    monkeypatch.setattr(
        judge,
        "load_model",
        lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: responses.pop(0))
            )
        ),
    )
    result, cost = judge._generate_raw_response("Grade the reply")
    assert result.choices[0].finish_reason == "stop" and cost is None
    validation = [e for e in judge.request_events if e.get("phase") == "validation"]
    assert len(validation) == 1 and validation[0]["error"] == "InvalidJudgeOutput"
