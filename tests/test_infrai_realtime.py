import httpx

from live_poll_service.infrai_realtime import InfraiRealtime


def test_publish_retries_429_with_the_same_idempotency_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"ok": False, "data": None, "error": {"code": "RATE_LIMITED"}},
            )
        return httpx.Response(
            200,
            json={"ok": True, "data": {"published": True}, "error": None, "metadata": {}},
        )

    client = InfraiRealtime(
        "test-key",
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )
    try:
        result = client.publish_result(
            "course-poll:opening-check",
            {"total_votes": 1},
            "educator-mira",
            "vote-opening-check-learner-42-request-1",
        )
    finally:
        client.close()

    assert result == {"published": True}
    assert len(seen) == 2
    assert {request.headers["Idempotency-Key"] for request in seen} == {
        "vote-opening-check-learner-42-request-1"
    }

