import httpx
import pytest
from paylane.provider import OpenRouter, ProviderError


def test_retryable_transport_error_is_bounded_and_reported():
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("unavailable")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"kind":"verify"}'}}],
                "usage": {},
            },
        )

    p = OpenRouter(
        key="test-only",
        client=httpx.Client(transport=httpx.MockTransport(handle)),
        sleep=lambda _: None,
    )
    r = p.complete([{"role": "user", "content": "Hi"}], [])
    assert len(calls) == 2 and r["_http_attempts"] == 2
    p.close()


def test_repeated_failure_opens_circuit_without_extra_network_requests():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(503)

    p = OpenRouter(
        key="test-only",
        client=httpx.Client(transport=httpx.MockTransport(handle)),
        sleep=lambda _: None,
    )
    for _ in range(3):
        with pytest.raises(ProviderError):
            p.complete([], [])
    count = len(calls)
    with pytest.raises(ProviderError, match="circuit_open"):
        p.complete([], [])
    assert len(calls) == count and count == 9
    p.close()


def test_inconsistent_risk_schema_fails_closed():
    def handle(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"route":"normal","reason":"legal","action":"refund_request"}'
                        }
                    }
                ]
            },
        )

    p = OpenRouter(
        key="test-only", client=httpx.Client(transport=httpx.MockTransport(handle))
    )
    with pytest.raises(ProviderError, match="invalid_risk_output"):
        p.classify([])
    p.close()


def test_tool_phase_does_not_compete_with_answer_json_format():
    import json

    payloads = []

    def handle(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "read",
                                    "type": "function",
                                    "function": {
                                        "name": "get_transaction",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        },
                    }
                ]
            },
        )

    p = OpenRouter(
        key="test-only", client=httpx.Client(transport=httpx.MockTransport(handle))
    )
    result = p.complete(
        [],
        [
            {
                "type": "function",
                "function": {
                    "name": "get_transaction",
                    "parameters": {"type": "object"},
                },
            }
        ],
        require_tool=True,
    )
    assert "response_format" not in payloads[0]
    assert payloads[0]["tool_choice"] == "required"
    assert result["_finish_reason"] == "tool_calls"
    p.close()


def test_classifier_repairs_incomplete_json_with_schema_and_records_all_usage():
    import json

    payloads = []

    def handle(request):
        payloads.append(json.loads(request.content))
        content = (
            '{"route":"normal"}'
            if len(payloads) == 1
            else '{"route":"normal","reason":"none","action":"refund_request"}'
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.01},
            },
        )

    p = OpenRouter(
        key="test-only", client=httpx.Client(transport=httpx.MockTransport(handle))
    )
    result = p.classify([{"role": "user", "content": "Refund TXN-OVER"}])
    assert result["action"] == "refund_request"
    assert len(payloads) == 2
    assert all(x["response_format"]["type"] == "json_schema" for x in payloads)
    assert result["_usage"]["prompt_tokens"] == 20 and result["_usage"]["cost"] == 0.02
    assert result["_contract_repairs"] == 1
    p.close()
