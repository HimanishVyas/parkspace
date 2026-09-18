"""Payment gateway abstraction (PRD §14).

Booking logic never talks to a gateway directly — it goes through `PaymentGateway`,
whose four operations are the entire surface a provider has to implement:

    create_payment()  verify_payment()  refund_payment()  parse_webhook()

Two implementations ship in V1: `MockGateway`, which exercises the full flow
offline (and is what the test suite and the sandbox use), and `RazorpayGateway`.
Swapping to another provider means adding a class here and changing one setting.

No card number, CVV or other cardholder data ever enters this module — the
gateway collects those on its own hosted form; we only ever see opaque ids.
"""
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    def __init__(self, message: str, code: str = "PAYMENT_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class SignatureError(PaymentError):
    def __init__(self, message: str = "Invalid payment signature"):
        super().__init__(message, code="INVALID_SIGNATURE")


@dataclass
class PaymentIntent:
    """What we ask the gateway to collect."""

    amount: Decimal
    currency: str
    reference: str
    description: str
    customer_email: str | None = None
    customer_name: str | None = None
    notes: dict[str, str] = field(default_factory=dict)


@dataclass
class GatewayOrder:
    order_id: str
    amount: Decimal
    currency: str
    # Everything the browser SDK needs to open the checkout.
    client_payload: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayPayment:
    payment_id: str
    order_id: str
    amount: Decimal
    status: str
    method: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayRefund:
    refund_id: str
    amount: Decimal
    status: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class GatewayWebhook:
    event_id: str
    event_type: str
    order_id: str | None
    payment_id: str | None
    status: str
    raw: dict[str, Any] = field(default_factory=dict)


class PaymentGateway(Protocol):
    name: str

    async def create_payment(self, intent: PaymentIntent) -> GatewayOrder: ...

    async def verify_payment(self, order_id: str, payment_id: str, signature: str) -> GatewayPayment: ...

    async def refund_payment(self, payment_id: str, amount: Decimal, reason: str | None) -> GatewayRefund: ...

    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> GatewayWebhook: ...


def _to_paise(amount: Decimal) -> int:
    """Gateways bill in the smallest currency unit."""
    return int((Decimal(amount) * 100).to_integral_value())


def _from_paise(value: int | str) -> Decimal:
    return (Decimal(str(value)) / 100).quantize(Decimal("0.01"))


# --------------------------------------------------------------------------- #
# Mock gateway — full flow, no network
# --------------------------------------------------------------------------- #
class MockGateway:
    """Simulates a gateway well enough to exercise every path end to end.

    The client 'pays' by signing `order_id|payment_id` with the shared secret,
    exactly as Razorpay's checkout does, so the verification code under test is
    the real one rather than a stub.
    """

    name = "mock"

    def __init__(self, secret: str | None = None):
        self._secret = (secret or settings.mock_gateway_secret).encode()

    def _sign(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()

    async def create_payment(self, intent: PaymentIntent) -> GatewayOrder:
        order_id = f"mock_order_{uuid.uuid4().hex[:16]}"
        return GatewayOrder(
            order_id=order_id,
            amount=intent.amount,
            currency=intent.currency,
            client_payload={
                "gateway": self.name,
                "order_id": order_id,
                "amount_paise": _to_paise(intent.amount),
                "currency": intent.currency,
                "description": intent.description,
                # Sandbox convenience: the checkout stub uses these to complete
                # a payment without a real card.
                "mock_payment_id": f"mock_pay_{uuid.uuid4().hex[:16]}",
            },
            raw={"order_id": order_id, "reference": intent.reference},
        )

    async def verify_payment(self, order_id: str, payment_id: str, signature: str) -> GatewayPayment:
        expected = self._sign(f"{order_id}|{payment_id}")
        if not hmac.compare_digest(expected, signature):
            raise SignatureError()
        return GatewayPayment(
            payment_id=payment_id,
            order_id=order_id,
            amount=Decimal("0"),  # caller trusts its own booking total
            status="captured",
            method="mock",
            raw={"order_id": order_id, "payment_id": payment_id},
        )

    async def refund_payment(self, payment_id: str, amount: Decimal, reason: str | None) -> GatewayRefund:
        return GatewayRefund(
            refund_id=f"mock_rfnd_{uuid.uuid4().hex[:16]}",
            amount=amount,
            status="processed",
            raw={"payment_id": payment_id, "reason": reason},
        )

    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> GatewayWebhook:
        signature = headers.get("x-mock-signature", "")
        expected = hmac.new(self._secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise SignatureError("Invalid webhook signature")
        payload = json.loads(body.decode())
        return GatewayWebhook(
            event_id=str(payload.get("event_id", uuid.uuid4())),
            event_type=str(payload.get("event", "payment.captured")),
            order_id=payload.get("order_id"),
            payment_id=payload.get("payment_id"),
            status=str(payload.get("status", "captured")),
            raw=payload,
        )


# --------------------------------------------------------------------------- #
# Razorpay
# --------------------------------------------------------------------------- #
class RazorpayGateway:
    name = "razorpay"
    api_base = "https://api.razorpay.com/v1"

    def __init__(self):
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise PaymentError("Razorpay credentials are not configured", code="GATEWAY_NOT_CONFIGURED")
        self._auth = (settings.razorpay_key_id, settings.razorpay_key_secret)
        self._secret = settings.razorpay_key_secret.encode()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            async with httpx.AsyncClient(timeout=15.0, auth=self._auth) as client:
                response = await client.request(method, f"{self.api_base}{path}", **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            logger.error("Razorpay %s %s failed: %s", method, path, detail)
            raise PaymentError("The payment gateway rejected the request", code="GATEWAY_REJECTED")
        except httpx.HTTPError as exc:
            logger.error("Razorpay %s %s unreachable: %s", method, path, exc)
            raise PaymentError("The payment gateway is unreachable", code="GATEWAY_UNAVAILABLE")

    async def create_payment(self, intent: PaymentIntent) -> GatewayOrder:
        payload = {
            "amount": _to_paise(intent.amount),
            "currency": intent.currency,
            "receipt": intent.reference,
            "notes": {**intent.notes, "reference": intent.reference},
        }
        data = await self._request("POST", "/orders", json=payload)
        return GatewayOrder(
            order_id=data["id"],
            amount=intent.amount,
            currency=intent.currency,
            client_payload={
                "gateway": self.name,
                "key_id": settings.razorpay_key_id,
                "order_id": data["id"],
                "amount_paise": data["amount"],
                "currency": data["currency"],
                "description": intent.description,
                "prefill": {"email": intent.customer_email, "name": intent.customer_name},
            },
            raw=data,
        )

    async def verify_payment(self, order_id: str, payment_id: str, signature: str) -> GatewayPayment:
        expected = hmac.new(self._secret, f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise SignatureError()
        data = await self._request("GET", f"/payments/{payment_id}")
        if data.get("order_id") != order_id:
            raise SignatureError("Payment does not belong to this order")
        return GatewayPayment(
            payment_id=data["id"],
            order_id=data["order_id"],
            amount=_from_paise(data["amount"]),
            status=data.get("status", "captured"),
            method=data.get("method"),
            raw=data,
        )

    async def refund_payment(self, payment_id: str, amount: Decimal, reason: str | None) -> GatewayRefund:
        payload: dict[str, Any] = {"amount": _to_paise(amount)}
        if reason:
            payload["notes"] = {"reason": reason[:255]}
        data = await self._request("POST", f"/payments/{payment_id}/refund", json=payload)
        return GatewayRefund(
            refund_id=data["id"],
            amount=_from_paise(data["amount"]),
            status=data.get("status", "processed"),
            raw=data,
        )

    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> GatewayWebhook:
        signature = headers.get("x-razorpay-signature", "")
        if not settings.razorpay_webhook_secret:
            raise PaymentError("Webhook secret is not configured", code="GATEWAY_NOT_CONFIGURED")
        expected = hmac.new(
            settings.razorpay_webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise SignatureError("Invalid webhook signature")
        payload = json.loads(body.decode())
        entity = (
            payload.get("payload", {}).get("payment", {}).get("entity", {})
            if isinstance(payload.get("payload"), dict)
            else {}
        )
        return GatewayWebhook(
            event_id=str(headers.get("x-razorpay-event-id") or payload.get("id") or uuid.uuid4()),
            event_type=str(payload.get("event", "")),
            order_id=entity.get("order_id"),
            payment_id=entity.get("id"),
            status=entity.get("status", ""),
            raw=payload,
        )


def get_gateway(name: str | None = None) -> PaymentGateway:
    selected = name or settings.payment_gateway
    if selected == "razorpay":
        return RazorpayGateway()
    return MockGateway()
