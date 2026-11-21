from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import ValidationError

from booking_tools import (
    BookingToolRegistry,
    BusinessApiClient,
    BusinessApiError,
    ToolRequestError,
    agora_tool_definitions,
)


class FakeBusinessApi:
    def __init__(self):
        self.calls = []
        self.bookings = {}
        self.payments = {}

    async def request(self, method, path, *, body=None):
        self.calls.append((method, path, body))
        if path == "/v1/bookings/validate":
            details = body or {}
            missing = [
                field
                for field in (
                    "pickup_location",
                    "destination",
                    "vehicle_category",
                    "passenger_count",
                )
                if not details.get(field)
            ]
            clarifications = {
                field: ["Secunderabad Railway Station", "Hyderabad Deccan Station"]
                for field in ("pickup_location", "destination")
                if details.get(field) == "Railway Station"
            }
            errors = []
            if details.get("vehicle_category") == "bike" and details.get("passenger_count", 1) > 1:
                errors.append("bike supports up to 1 passenger.")
            return {
                "valid": not missing and not clarifications and not errors,
                "missing_fields": missing,
                "clarifications": clarifications,
                "errors": errors,
            }
        if path == "/v1/fare-estimates":
            return {
                "status": "estimated",
                "fare": 120,
                "currency": "INR",
                "distance_km": 5.0,
            }
        if path == "/v1/bookings":
            booking_id = "00000000-0000-0000-0000-000000000001"
            self.bookings[booking_id] = {
                "booking_id": booking_id,
                "booking_reference": "BR-00000000",
                "status": "CONFIRMED",
                "estimated_fare": body["booking_details"]["estimated_fare"],
                "payment_confirmed": False,
            }
            return self.bookings[booking_id]
        if path.startswith("/v1/bookings/") and path.endswith("/cancel"):
            booking_id = path.split("/")[-2]
            self.bookings[booking_id]["status"] = "CANCELLED"
            return self.bookings[booking_id]
        if path.startswith("/v1/bookings/"):
            return self.bookings[path.rsplit("/", 1)[-1]]
        if path == "/v1/payment-orders":
            payment_id = "00000000-0000-0000-0000-000000000002"
            self.payments[payment_id] = {
                "payment_id": payment_id,
                "booking_id": body["booking_id"],
                "status": "CREATED",
                "amount_minor": 12000,
                "currency": "INR",
            }
            return self.payments[payment_id]
        if path.startswith("/v1/payments/") and path.endswith("/simulate-result"):
            payment_id = path.split("/")[-2]
            self.payments[payment_id]["status"] = "PENDING"
            return self.payments[payment_id]
        if path.startswith("/v1/payments/") and path.endswith("/verify"):
            payment_id = path.split("/")[-2]
            payment = self.payments[payment_id]
            if payment["status"] != "PENDING":
                raise BusinessApiError(
                    409,
                    {
                        "detail": {
                            "code": "payment_not_verifiable",
                            "message": "A successful simulated result is required.",
                        }
                    },
                )
            self.payments[payment_id]["status"] = "VERIFIED"
            self.bookings[payment["booking_id"]]["payment_confirmed"] = True
            return payment
        if path.startswith("/v1/payments/"):
            return self.payments[path.rsplit("/", 1)[-1]]
        raise AssertionError(f"Unexpected business API request: {method} {path}")


def _booking_details():
    return {
        "passenger_name": "Asha",
        "pickup_location": "Madhapur",
        "destination": "Gachibowli",
        "vehicle_category": "bike",
        "passenger_count": 1,
        "payment_preference": "upi",
    }


def test_details_accumulate_corrections_invalidate_fare_and_revalidate():
    async def run():
        api = FakeBusinessApi()
        registry = BookingToolRegistry(api)
        token = registry.create_session()

        partial = await registry.invoke(
            token,
            "validate_booking_details",
            {
                "passenger_name": None,
                "pickup_location": "Madhapur",
                "destination": None,
                "vehicle_category": None,
                "passenger_count": None,
                "payment_preference": None,
            },
        )
        assert partial["status"] == "needs_details"
        assert "destination" in partial["missing_fields"]

        valid = await registry.invoke(token, "validate_booking_details", _booking_details())
        assert valid["valid"] is True
        estimate = await registry.invoke(token, "estimate_fare", {})
        assert estimate["fare"] == 120

        corrected = await registry.invoke(
            token,
            "validate_booking_details",
            {
                **_booking_details(),
                "destination": "Hitech City",
            },
        )
        assert corrected["valid"] is True
        with pytest.raises(ToolRequestError) as error:
            await registry.invoke(token, "create_booking", {"explicit_confirmation": "yes"})
        assert error.value.code == "fare_not_confirmable"

    asyncio.run(run())


def test_ambiguous_location_requires_clarification():
    async def run():
        registry = BookingToolRegistry(FakeBusinessApi())
        token = registry.create_session()
        result = await registry.invoke(
            token,
            "validate_booking_details",
            {
                **_booking_details(),
                "pickup_location": "Railway Station",
            },
        )
        assert result["valid"] is False
        assert result["clarifications"]["pickup_location"] == [
            "Secunderabad Railway Station",
            "Hyderabad Deccan Station",
        ]

    asyncio.run(run())


def test_booking_requires_explicit_confirmation_and_reuses_booking():
    async def run():
        api = FakeBusinessApi()
        registry = BookingToolRegistry(api)
        token = registry.create_session()
        await registry.invoke(token, "validate_booking_details", _booking_details())
        await registry.invoke(token, "estimate_fare", {})

        with pytest.raises(ValidationError):
            await registry.invoke(token, "create_booking", {"explicit_confirmation": "maybe"})

        first = await registry.invoke(
            token,
            "create_booking",
            {"explicit_confirmation": "yes"},
        )
        replay = await registry.invoke(
            token,
            "create_booking",
            {"explicit_confirmation": "yes"},
        )
        assert first["booking"]["status"] == "CONFIRMED"
        assert replay["idempotent_replay"] is True
        assert sum(path == "/v1/bookings" for _, path, _ in api.calls) == 1

    asyncio.run(run())


def test_cancel_before_confirmation_discards_only_conversation_state():
    async def run():
        api = FakeBusinessApi()
        registry = BookingToolRegistry(api)
        token = registry.create_session()
        await registry.invoke(token, "validate_booking_details", _booking_details())

        cancelled = await registry.invoke(token, "cancel_booking", {})
        assert cancelled == {"status": "cancelled", "booking_created": False}
        assert not any(path == "/v1/bookings" for _, path, _ in api.calls)

        result = await registry.invoke(
            token,
            "validate_booking_details",
            {**_booking_details(), "destination": "Hitech City"},
        )
        assert result["collected_details"]["destination"] == "Hitech City"

    asyncio.run(run())


def test_payment_order_is_not_success_and_only_backend_verify_confirms():
    async def run():
        api = FakeBusinessApi()
        registry = BookingToolRegistry(api)
        token = registry.create_session()
        await registry.invoke(token, "validate_booking_details", _booking_details())
        await registry.invoke(token, "estimate_fare", {})
        booking = await registry.invoke(token, "create_booking", {"explicit_confirmation": "yes"})
        payment = await registry.invoke(token, "create_payment_order", {})
        assert payment["payment"]["status"] == "CREATED"

        definitions = agora_tool_definitions("https://voice.example.com")
        names = {tool["function"]["name"] for tool in definitions}
        assert "simulate_payment_result" not in names
        with pytest.raises(BusinessApiError) as error:
            await registry.invoke(token, "verify_payment", {})
        assert error.value.status_code == 409
        await api.request(
            "POST",
            f"/v1/payments/{payment['payment']['payment_id']}/simulate-result",
            body={"outcome": "success"},
        )
        assert api.payments[payment["payment"]["payment_id"]]["status"] == "PENDING"
        verified = await registry.invoke(token, "verify_payment", {})
        assert verified["status"] == "VERIFIED"
        assert api.bookings[booking["booking"]["booking_id"]]["payment_confirmed"] is True

    asyncio.run(run())


def test_business_api_client_auth_errors_and_timeout_are_explicit():
    seen_headers = []

    async def unavailable(request):
        seen_headers.append(request.headers)
        return httpx.Response(503, json={"detail": {"code": "unavailable"}})

    async def timeout(_request):
        raise httpx.ConnectTimeout("upstream timed out")

    async def run():
        api = BusinessApiClient(
            "https://business.example.com",
            "server-only-key",
            transport=httpx.MockTransport(unavailable),
        )
        with pytest.raises(BusinessApiError) as error:
            await api.request("POST", "/v1/fare-estimates", body={})
        assert error.value.status_code == 503
        assert seen_headers[0]["X-API-Key"] == "server-only-key"

        api = BusinessApiClient(
            "https://business.example.com",
            "server-only-key",
            transport=httpx.MockTransport(timeout),
        )
        with pytest.raises(ToolRequestError) as timeout_error:
            await api.request("POST", "/v1/fare-estimates", body={})
        assert timeout_error.value.status_code == 504
        assert timeout_error.value.code == "business_api_timeout"

    asyncio.run(run())
