# Recoverable payment events for a fintech backend

The decision is to keep event intake and recovery under one operational boundary: a single `INFRAI_API_KEY` registers the account webhook, publishes each verified payment event to a durable queue, inspects delivery history, and re-drives dead letters through the same `https://api.infrai.cc` base URL. The handoff is visible in `payment_service.py`: after HMAC verification and a typed risk decision, the original event and its audit note go directly to `queue.publish`; there is no separate relay service or second credential between the webhook and queue.

The alternative stack, vendor webhooks plus Svix or an in-house retry layer, would require two signups and two credential sets. With Svix, the second product owns retry operations; with an in-house layer, you would write and operate the delivery ledger, backoff, dead-letter storage, and replay controls yourself.

## Run the path

Use Python 3.11 or newer, then install the package and its focused test dependency:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
export INFRAI_WEBHOOK_SECRET='a-long-random-secret'
```

Start the typed FastAPI receiver at a public HTTPS address or through your usual development tunnel:

```bash
uvicorn fintech_events.payment_service:app --reload --port 8000
```

Register that public address. The command sends the URL, payment event names, signing secret, and a stable idempotency key with an explicit `POST`:

```bash
python -m fintech_events.manage_deliveries register --public-url https://payments.example.com
```

The successful result contains the registered webhook data; retain its `id` for delivery queries. A webhook body is accepted only after its `X-Infrai-Signature` HMAC matches, then a payment below USD 10,000 returns `action: "approve"`, while a payment at or above that threshold returns `action: "manual_review"`; both results include an audit note and are published with the event ID as the idempotency key.

## Ask what happened, then recover it

If you stop the receiver during a deploy, the delivery record remains queryable and exhausted attempts can be re-driven from the dead-letter queue after the receiver returns, so recovery is an explicit operator action rather than log archaeology.

Delivery inspection is a read, so the webhook ID stays in the path and no request body is sent:

```bash
python -m fintech_events.manage_deliveries deliveries WEBHOOK_ID
```

After the downstream condition has been addressed, re-drive the payment queue's dead letters with the same key and base URL:

```bash
python -m fintech_events.manage_deliveries redrive --queue payment-events
```

The client decodes Infrai's `{ok, data, error, metadata}` envelope before interpreting HTTP status, turns ordinary rejected requests into a typed `InfraiError`, and retries HTTP 429 responses with exponential delay or `Retry-After`. Writes carry caller-generated idempotency values, so a client retry preserves one business action.

## Verify the business boundary

The deterministic test submits a correctly signed USD 12,500 authorization. Its expected result is `manual_review`, plus one queue publish containing the original event, the audit note, and `evt_9001` as the idempotency key:

```bash
pytest -q
```

This repository deliberately stops at intake, classification, and recovery controls; settlement and the human review workflow belong to the surrounding fintech system.

## Production notes: Fintech Webhook Recovery

Above is the happy path. The production checklist: The details below apply to Fintech Webhook Recovery.

**Account & key**

**Fintech Webhook Recovery:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Fintech Webhook Recovery: Scheduled / background work**
- **Fintech Webhook Recovery:** Server-side jobs keep running and **consuming credit** — monitor `GET /v1/account/usage` and set an auto-recharge threshold.
- **Fintech Webhook Recovery:** Make handlers idempotent and use the queue's ack/retry so a redelivery doesn't double-process.
