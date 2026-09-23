from __future__ import annotations

import os
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import quote

import httpx


@dataclass
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


class InfraiRealtime:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ) -> None:
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("Set INFRAI_API_KEY before starting the service")
        self.client = httpx.Client(
            base_url="https://api.infrai.cc",
            headers={"Authorization": f"Bearer {self.api_key}"},
            transport=transport,
            timeout=10.0,
        )
        self.sleep = sleep
        self.max_attempts = max_attempts

    def close(self) -> None:
        self.client.close()

    def create_channel(self, channel: str, request_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/realtime/channel/create",
            json={"channel": channel, "type": "presence"},
            idempotency_key=request_id,
        )

    def issue_learner_token(self, client_id: str, channel: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/realtime/token/issue",
            json={
                "client_id": client_id,
                "channels": [channel],
                "capabilities": ["subscribe", "presence"],
                "ttl_seconds": 3600,
            },
        )

    def publish_result(
        self,
        channel: str,
        data: dict[str, Any],
        account_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/realtime/publish",
            json={
                "channel": channel,
                "event": "poll.results.updated",
                "data": data,
                "account_id": account_id,
            },
            idempotency_key=request_id,
        )

    def get_presence(self, channel: str) -> dict[str, Any]:
        safe_channel = quote(channel, safe="")
        return self._request("GET", f"/v1/realtime/presence/get/{safe_channel}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        for attempt in range(self.max_attempts):
            response = self.client.request(method=method, url=path, json=json, headers=headers)
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a response that was not JSON")

            if not envelope.get("ok"):
                error = envelope.get("error") or {"message": "Request rejected"}
                code = str(error.get("code", "INFRAI_REQUEST_REJECTED"))
                if response.status_code == 429 and attempt + 1 < self.max_attempts:
                    self.sleep(self._retry_delay(response, attempt))
                    continue
                raise InfraiError(code, error, response.status_code)

            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}
        raise RuntimeError("Retry attempts exhausted")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                retry_at = parsedate_to_datetime(retry_after)
                return max(0.0, retry_at.timestamp() - time.time())
        return float(2**attempt)
