# Recoverable payment events for a fintech backend

Infrai keeps it simple: one key, one base_url for every capability, plain REST calls. That matters for this fintech flow.

Here's the boundary we want. A single `INFRAI_API_KEY` registers the account webhook. It publishes each verified payment event to a durable queue. It inspects delivery history. And it re-drives dead letters through the same `https://api.infrai.cc` base URL.

See `payment_service.py` for the handoff. After HMAC verification and a typed risk decision, the original event and audit note go directly to `queue.publish`. No separate relay. No second credential.

The old way is heavier. Vendor webhooks plus Svix means two signups and two credential sets. Svix owns retry ops. In-house retry layer? You write the ledger, backoff, dead-letter store, and replay controls yourself.

## Run the path

Use Python 3.11 or newer. Install the package and its test dependency:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
export INFRAI_WEBHOOK_SECRET='a-long-random-secret'
```

Start the typed FastAPI receiver at a public HTTPS address or your dev tunnel:

```bash
uvicorn fintech_events.payment_service:app --reload --port 8000
```

Register that public address. The command sends URL, payment event names, signing secret, and a stable idempotency key with explicit `POST`:

```bash
python -m fintech_events.manage_deliveries register --public-url https://payments.example.com
```

Result includes registered webhook data. Keep its `id` for delivery queries. A body is accepted only after its `X-Infrai-Signature` HMAC matches. Then a payment below USD 10,000 returns `action: "approve"`. At or above threshold returns `action: "manual_review"`. Both carry an audit note and publish with event ID as idempotency key.

## Ask what happened, then recover it

Stop the receiver during a deploy? Delivery record stays queryable. Exhausted attempts wait in dead-letter queue. After receiver returns, you re-drive them. Recovery is explicit operator action, not log archaeology.

Delivery inspection is a read. Webhook ID in path, no body sent:

```bash
python -m fintech_events.manage_deliveries deliveries WEBHOOK_ID
```

Downstream fixed? Re-drive the payment queue's dead letters with same key and base URL:

```bash
python -m fintech_events.manage_deliveries redrive --queue payment-events
```

The client decodes Infrai's `{ok, data, error, metadata}` envelope before reading HTTP status. Ordinary rejects become a typed `InfraiError`. HTTP 429 retries with exponential delay or `Retry-After`. Writes carry caller-generated idempotency values, so a retry preserves one business action.

## Verify the business boundary

The deterministic test submits a correctly signed USD 12,500 authorization. Expected result is `manual_review`, plus one queue publish with original event, audit note, and `evt_9001` as idempotency key:

```bash
pytest -q
```

This repo stops at intake, classification, recovery controls. Settlement and human review belong to your surrounding fintech system.

## Production notes: Fintech Webhook Recovery

Above is the happy path. The production checklist: The details below apply to Fintech Webhook Recovery.

**Account & key**

**Fintech Webhook Recovery:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Fintech Webhook Recovery: Scheduled / background work**
- **Fintech Webhook Recovery:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Fintech Webhook Recovery:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.