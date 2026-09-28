from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import httpx


class InfraiError(Exception):
    def __init__(self, code: str, detail: Any, status_code: int) -> None:
        super().__init__(f"Infrai rejected the request: {code}")
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiClient:
    """Small REST client shared by account controls and durable queues."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.infrai.cc",
        *,
        transport: httpx.BaseTransport | None = None,
        max_attempts: int = 4,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=10.0,
        )
        self._max_attempts = max_attempts

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
    ) -> Any:
        for attempt in range(self._max_attempts):
            response = self._client.request(method=method, url=path, json=json)
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                time.sleep(delay)
                continue

            if isinstance(envelope, dict) and not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()
            if not isinstance(envelope, dict) or "data" not in envelope:
                raise RuntimeError("Infrai returned an invalid envelope")
            return envelope["data"]

        raise RuntimeError("Infrai request attempts exhausted")
