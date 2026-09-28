from __future__ import annotations

import hashlib
import hmac
import os
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .infrai_client import InfraiClient, InfraiError


class PaymentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: Literal["payment.authorized", "payment.captured"]
    payment_id: str = Field(min_length=1)
    amount_usd: float = Field(gt=0)
    account_id: str = Field(min_length=1)


class IntakeResult(BaseModel):
    event_id: str
    action: Literal["approve", "manual_review"]
    audit_note: str
    queued: bool


def verify_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    supplied = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, supplied)


def assess_payment(event: PaymentEvent) -> IntakeResult:
    if event.amount_usd >= 10_000:
        return IntakeResult(
            event_id=event.event_id,
            action="manual_review",
            audit_note=f"Payment {event.payment_id} held for high-value review",
            queued=True,
        )
    return IntakeResult(
        event_id=event.event_id,
        action="approve",
        audit_note=f"Payment {event.payment_id} approved by amount policy",
        queued=True,
    )


def create_app(client: InfraiClient | None = None) -> FastAPI:
    app = FastAPI(title="Payment event intake")

    @app.post("/payment-events", response_model=IntakeResult)
    async def receive_payment(
        request: Request,
        x_infrai_signature: str = Header(alias="X-Infrai-Signature"),
    ) -> IntakeResult:
        raw_body = await request.body()
        secret = os.environ["INFRAI_WEBHOOK_SECRET"]
        if not verify_signature(raw_body, x_infrai_signature, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        event = PaymentEvent.model_validate_json(raw_body)
        decision = assess_payment(event)
        active_client = client or InfraiClient(os.environ["INFRAI_API_KEY"])
        try:
            active_client.request(
                "POST",
                "/v1/queue/publish",
                json={
                    "queue": "payment-events",
                    "payload": {"event": event.model_dump(), "decision": decision.model_dump()},
                    "idempotency_key": event.event_id,
                },
            )
        except InfraiError as exc:
            raise HTTPException(
                status_code=exc.status_code if 400 <= exc.status_code < 500 else 502,
                detail={"code": exc.code, "detail": exc.detail},
            ) from exc
        return decision

    return app


app = create_app()
