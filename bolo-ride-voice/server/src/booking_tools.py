from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field


class BusinessApiError(Exception):
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"Business API returned HTTP {status_code}")


class ToolRequestError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class BusinessApiClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 8.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                headers={"X-API-Key": self.api_key},
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.request(method, path, json=body)
        except httpx.TimeoutException as exc:
            raise ToolRequestError(
                504,
                "business_api_timeout",
                "The booking service timed out. No result has been confirmed; please retry.",
            ) from exc
        except httpx.RequestError as exc:
            raise ToolRequestError(
                503,
                "business_api_unavailable",
                "The booking service is unavailable. Please try again.",
            ) from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {"detail": "The booking service returned an invalid response."}
        if not response.is_success:
            raise BusinessApiError(response.status_code, payload)
        if not isinstance(payload, dict):
            raise ToolRequestError(
                502,
                "business_api_invalid_response",
                "The booking service returned an unexpected response.",
            )
        return payload


class BookingDetailsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    passenger_name: str | None = Field(default=None, min_length=1, max_length=120)
    pickup_location: str | None = Field(default=None, min_length=2, max_length=200)
    destination: str | None = Field(default=None, min_length=2, max_length=200)
    vehicle_category: Literal["bike", "auto", "sedan"] | None = None
    passenger_count: int | None = Field(default=None, ge=1, le=6)
    payment_preference: Literal["cash", "upi", "card"] | None = None


class ExplicitConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explicit_confirmation: Literal["yes"]


@dataclass
class BookingConversationState:
    details: dict[str, Any] = field(
        default_factory=lambda: {
            "passenger_name": None,
            "pickup_location": None,
            "destination": None,
            "vehicle_category": None,
            "passenger_count": None,
            "payment_preference": None,
        }
    )
    estimate: dict[str, Any] | None = None
    booking: dict[str, Any] | None = None
    payment: dict[str, Any] | None = None
    booking_idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    payment_idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class _ToolSession:
    state: BookingConversationState = field(default_factory=BookingConversationState)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _nullable_string_schema(*, enum: list[str] | None = None) -> dict[str, Any]:
    string_schema: dict[str, Any] = {"type": "string"}
    if enum:
        string_schema["enum"] = enum
    return {"anyOf": [string_schema, {"type": "null"}]}


def _tool_schema(name: str) -> dict[str, Any]:
    if name == "validate_booking_details":
        properties: dict[str, Any] = {
            "passenger_name": _nullable_string_schema(),
            "pickup_location": _nullable_string_schema(),
            "destination": _nullable_string_schema(),
            "vehicle_category": _nullable_string_schema(enum=["bike", "auto", "sedan"]),
            "passenger_count": {
                "anyOf": [{"type": "integer", "minimum": 1, "maximum": 6}, {"type": "null"}]
            },
            "payment_preference": _nullable_string_schema(enum=["cash", "upi", "card"]),
        }
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }
    if name == "create_booking":
        return {
            "type": "object",
            "properties": {
                "explicit_confirmation": {
                    "type": "string",
                    "enum": ["yes"],
                    "description": "Use only after the passenger explicitly confirms the read-back fare.",
                }
            },
            "required": ["explicit_confirmation"],
            "additionalProperties": False,
        }
    return {"type": "object", "properties": {}, "required": [], "additionalProperties": False}


_TOOL_DESCRIPTIONS = {
    "validate_booking_details": (
        "Save or correct trip details and validate them. Send null for information not yet provided; "
        "the tool preserves previously collected values and returns missing fields or location clarifications."
    ),
    "estimate_fare": (
        "Estimate the fare using the validated trip details already collected. Call after required details are valid."
    ),
    "create_booking": (
        "Create a booking only after the passenger explicitly confirms the read-back trip and fare. "
        "Set explicit_confirmation to yes only for a clear affirmative response."
    ),
    "get_booking_status": "Retrieve the backend status for this conversation's confirmed booking.",
    "cancel_booking": (
        "Cancel the draft before booking, or request cancellation of the confirmed booking through the backend."
    ),
    "create_payment_order": (
        "Create a mock payment order for this confirmed booking after the passenger asks to proceed with payment. "
        "This does not mean payment succeeded."
    ),
    "get_payment_status": "Retrieve the backend status of this booking's payment.",
    "verify_payment": (
        "Ask the backend to verify a pending payment. Report success only when the returned status is VERIFIED."
    ),
}

_TOOL_NAMES = tuple(_TOOL_DESCRIPTIONS)


def agora_tool_definitions(public_url: str) -> list[dict[str, Any]]:
    tool_definitions: list[dict[str, Any]] = []
    for name, description in _TOOL_DESCRIPTIONS.items():
        if name == "validate_booking_details":
            body = {key: f"{{{{args.{key}}}}}" for key in BookingDetailsInput.model_fields}
        elif name == "create_booking":
            body = {"explicit_confirmation": "{{args.explicit_confirmation}}"}
        else:
            body = {}
        tool_definitions.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": _tool_schema(name),
                },
                "server": {
                    "method": "POST",
                    "url": f"{public_url.rstrip('/')}/v1/agent-tools/{name}",
                    "headers": {
                        "Authorization": "Bearer {{template_variables.bolo_tool_token}}"
                    },
                    "body": body,
                    "timeout_ms": 10_000,
                },
            }
        )
    return tool_definitions


class BookingToolRegistry:
    def __init__(self, business_api: BusinessApiClient) -> None:
        self.business_api = business_api
        self._sessions: dict[str, _ToolSession] = {}

    def create_session(self) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[self._token_digest(token)] = _ToolSession()
        return token

    def revoke_session(self, token: str | None) -> None:
        if token:
            self._sessions.pop(self._token_digest(token), None)

    async def invoke(
        self,
        token: str,
        tool_name: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        session = self._sessions.get(self._token_digest(token))
        if session is None:
            raise ToolRequestError(401, "invalid_tool_session", "This voice session is no longer active.")
        if tool_name not in _TOOL_NAMES:
            raise ToolRequestError(404, "tool_not_found", "This booking action is not available.")

        async with session.lock:
            handler = getattr(self, f"_{tool_name}")
            return await handler(session.state, payload)

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def _validate_booking_details(
        self,
        state: BookingConversationState,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        request = BookingDetailsInput.model_validate(payload)
        if state.booking is not None:
            raise ToolRequestError(
                409,
                "booking_already_created",
                "The confirmed booking cannot be edited. Cancel it or retrieve its status.",
            )

        changed = False
        for field_name, value in request.model_dump().items():
            if value is not None and state.details[field_name] != value:
                state.details[field_name] = value
                changed = True
        if changed:
            state.estimate = None
            state.booking_idempotency_key = str(uuid.uuid4())

        validation = await self.business_api.request(
            "POST",
            "/v1/bookings/validate",
            body=state.details,
        )
        return {
            "status": "valid" if validation.get("valid") else "needs_details",
            **validation,
            "collected_details": state.details,
        }

    async def _estimate_fare(
        self,
        state: BookingConversationState,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if payload:
            raise ToolRequestError(422, "unexpected_arguments", "Fare estimation takes no arguments.")
        if state.booking is not None:
            return {"status": "booking_exists", "booking": state.booking}
        validation = await self.business_api.request(
            "POST",
            "/v1/bookings/validate",
            body=state.details,
        )
        if not validation.get("valid"):
            return {"status": "needs_details", **validation}

        estimate = await self.business_api.request(
            "POST",
            "/v1/fare-estimates",
            body={
                "pickup": state.details["pickup_location"],
                "destination": state.details["destination"],
                "vehicle_category": state.details["vehicle_category"],
                "passenger_count": state.details["passenger_count"],
            },
        )
        if estimate.get("status") != "estimated" or estimate.get("fare") is None:
            state.estimate = None
            return {"status": "needs_clarification", **estimate}

        state.estimate = estimate
        return {
            "status": "estimated",
            "fare": estimate["fare"],
            "currency": estimate.get("currency", "INR"),
            "distance_km": estimate.get("distance_km"),
            "trip_details": state.details,
            "next_step": "Read back the trip and fare, then ask for explicit passenger confirmation.",
        }

    async def _create_booking(
        self,
        state: BookingConversationState,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        request = ExplicitConfirmationInput.model_validate(payload)
        if state.booking is not None:
            return {"status": "created", "booking": state.booking, "idempotent_replay": True}
        if state.estimate is None or state.estimate.get("status") != "estimated":
            raise ToolRequestError(
                409,
                "fare_not_confirmable",
                "A current fare estimate is required before booking.",
            )

        booking_details = {
            **state.details,
            "estimated_fare": state.estimate["fare"],
            "booking_confirmation": request.explicit_confirmation == "yes",
        }
        booking = await self.business_api.request(
            "POST",
            "/v1/bookings",
            body={
                "booking_details": booking_details,
                "idempotency_key": state.booking_idempotency_key,
            },
        )
        state.booking = booking
        state.payment = None
        state.payment_idempotency_key = str(uuid.uuid4())
        return {"status": "created", "booking": booking}

    async def _get_booking_status(
        self,
        state: BookingConversationState,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if payload:
            raise ToolRequestError(422, "unexpected_arguments", "Booking status takes no arguments.")
        if state.booking is None:
            raise ToolRequestError(404, "booking_not_found", "No confirmed booking exists in this conversation.")
        booking = await self.business_api.request(
            "GET",
            f"/v1/bookings/{state.booking['booking_id']}",
        )
        state.booking = booking
        return {"status": "retrieved", "booking": booking}

    async def _cancel_booking(
        self,
        state: BookingConversationState,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if payload:
            raise ToolRequestError(422, "unexpected_arguments", "Cancellation takes no arguments.")
        if state.booking is None:
            state.details = BookingConversationState().details
            state.estimate = None
            state.booking_idempotency_key = str(uuid.uuid4())
            state.payment_idempotency_key = str(uuid.uuid4())
            state.payment = None
            return {"status": "cancelled", "booking_created": False}
        booking = await self.business_api.request(
            "POST",
            f"/v1/bookings/{state.booking['booking_id']}/cancel",
            body={},
        )
        state.booking = booking
        return {"status": "cancelled", "booking": booking}

    async def _create_payment_order(
        self,
        state: BookingConversationState,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if payload:
            raise ToolRequestError(422, "unexpected_arguments", "Payment order creation takes no arguments.")
        if state.booking is None:
            raise ToolRequestError(
                409,
                "booking_required",
                "A confirmed booking is required before creating a payment order.",
            )
        if state.payment is not None:
            return {"status": "created", "payment": state.payment, "idempotent_replay": True}
        payment = await self.business_api.request(
            "POST",
            "/v1/payment-orders",
            body={
                "booking_id": state.booking["booking_id"],
                "idempotency_key": state.payment_idempotency_key,
            },
        )
        state.payment = payment
        return {"status": "created", "payment": payment}

    async def _get_payment_status(
        self,
        state: BookingConversationState,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if payload:
            raise ToolRequestError(422, "unexpected_arguments", "Payment status takes no arguments.")
        if state.payment is None:
            raise ToolRequestError(404, "payment_not_found", "No payment order exists in this conversation.")
        payment = await self.business_api.request("GET", f"/v1/payments/{state.payment['payment_id']}")
        state.payment = payment
        return {"status": "retrieved", "payment": payment}

    async def _verify_payment(
        self,
        state: BookingConversationState,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if payload:
            raise ToolRequestError(422, "unexpected_arguments", "Payment verification takes no arguments.")
        if state.payment is None:
            raise ToolRequestError(404, "payment_not_found", "No payment order exists in this conversation.")
        payment = await self.business_api.request(
            "POST",
            f"/v1/payments/{state.payment['payment_id']}/verify",
            body={},
        )
        state.payment = payment
        if payment.get("status") == "VERIFIED" and state.booking is not None:
            state.booking = await self.business_api.request(
                "GET",
                f"/v1/bookings/{state.booking['booking_id']}",
            )
        return {"status": payment.get("status"), "payment": payment}
