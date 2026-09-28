from __future__ import annotations

import argparse
import json
import os
import uuid
from typing import Any

from .infrai_client import InfraiClient


def register(client: InfraiClient, public_url: str, secret: str) -> Any:
    return client.request(
        "POST",
        "/v1/account/webhooks/register",
        json={
            "url": f"{public_url.rstrip('/')}/payment-events",
            "events": ["payment.authorized", "payment.captured"],
            "description": "Signed payment events for risk decisions",
            "secret": secret,
            "idempotency_key": str(uuid.uuid5(uuid.NAMESPACE_URL, public_url)),
        },
    )


def deliveries(client: InfraiClient, webhook_id: str) -> Any:
    return client.request("GET", f"/v1/account/webhooks/deliveries/{webhook_id}")


def redrive(client: InfraiClient, queue: str) -> Any:
    return client.request(
        "POST",
        f"/v1/queue/dlq/redrive/{queue}",
        json={
            "queue": queue,
            "idempotency_key": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"redrive:{queue}")),
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage payment event delivery")
    commands = parser.add_subparsers(dest="command", required=True)
    register_parser = commands.add_parser("register")
    register_parser.add_argument("--public-url", required=True)
    commands.add_parser("deliveries").add_argument("webhook_id")
    redrive_parser = commands.add_parser("redrive")
    redrive_parser.add_argument("--queue", default="payment-events")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = InfraiClient(os.environ["INFRAI_API_KEY"])
    try:
        if args.command == "register":
            result = register(client, args.public_url, os.environ["INFRAI_WEBHOOK_SECRET"])
        elif args.command == "deliveries":
            result = deliveries(client, args.webhook_id)
        else:
            result = redrive(client, args.queue)
        print(json.dumps(result, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
