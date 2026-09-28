import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from fintech_events.payment_service import create_app


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def request(self, method: str, path: str, *, json: dict[str, object]) -> dict[str, str]:
        self.calls.append((method, path, json))
        return {"message_id": "msg_123"}


def test_high_value_payment_is_signed_held_and_queued(monkeypatch) -> None:
    secret = "local-test-secret"
    monkeypatch.setenv("INFRAI_WEBHOOK_SECRET", secret)
    event = {
        "event_id": "evt_9001",
        "event_type": "payment.authorized",
        "payment_id": "pay_42",
        "amount_usd": 12500,
        "account_id": "acct_7",
    }
    raw_body = json.dumps(event, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    infrai = RecordingClient()

    response = TestClient(create_app(infrai)).post(
        "/payment-events",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Infrai-Signature": f"sha256={signature}"},
    )

    assert response.status_code == 200
    assert response.json()["action"] == "manual_review"
    assert response.json()["queued"] is True
    method, path, body = infrai.calls[0]
    assert (method, path) == ("POST", "/v1/queue/publish")
    assert body["idempotency_key"] == "evt_9001"
    assert body["payload"]["decision"]["action"] == "manual_review"
