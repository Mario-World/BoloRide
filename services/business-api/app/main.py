from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import Database
from .models import Booking, BookingStatusEvent, Payment, PaymentStatusEvent
from .provider import SimulatedRideProvider
from .schemas import (
    BookingDraftDetails,
    BookingResponse,
    BookingStatus,
    BookingValidationResponse,
    CreateBookingRequest,
    DriverAssignmentOutcome,
    DriverDetails,
    DriverSimulationRequest,
    FareEstimateRequest,
    FareEstimateResponse,
    MockPaymentOutcome,
    PaymentOrderRequest,
    PaymentResponse,
    PaymentSimulationRequest,
    PaymentStatus,
)

logger = logging.getLogger("uvicorn.error")

BOOKING_TRANSITIONS = {
    BookingStatus.CONFIRMED: {
        BookingStatus.DRIVER_ASSIGNED,
        BookingStatus.CANCELLED,
        BookingStatus.FAILED,
    },
    BookingStatus.DRIVER_ASSIGNED: {
        BookingStatus.COMPLETED,
        BookingStatus.CANCELLED,
        BookingStatus.FAILED,
    },
}

PAYMENT_TERMINAL_STATES = {
    PaymentStatus.VERIFIED,
    PaymentStatus.FAILED,
    PaymentStatus.CANCELLED,
    PaymentStatus.EXPIRED,
}


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_key: str
    simulator_enabled: bool = False
    auto_create_schema: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+asyncpg://bolo:replace-me@localhost:5432/bolo_ride",
            ),
            api_key=os.getenv("BUSINESS_API_KEY", ""),
            simulator_enabled=os.getenv("MOCK_PAYMENTS_ENABLED", "false").casefold()
            == "true",
        )


def _validate_details(
    details: BookingDraftDetails,
    provider: SimulatedRideProvider,
) -> BookingValidationResponse:
    missing_fields = [
        name
        for name in (
            "pickup_location",
            "destination",
            "vehicle_category",
            "passenger_count",
        )
        if getattr(details, name) is None
    ]
    clarifications: dict[str, list[str]] = {}
    errors: list[str] = []
    for field in ("pickup_location", "destination"):
        value = getattr(details, field)
        if value is not None:
            resolution = provider.resolve_location(value)
            if resolution.canonical_name is None:
                clarifications[field] = list(resolution.candidates) or [
                    "Please provide a specific Hyderabad locality or landmark."
                ]

    if details.pickup_location and details.destination:
        pickup = provider.resolve_location(details.pickup_location)
        destination = provider.resolve_location(details.destination)
        if (
            pickup.canonical_name is not None
            and pickup.canonical_name == destination.canonical_name
        ):
            errors.append("Pickup and destination must be different locations.")

    if (
        details.vehicle_category is not None
        and details.passenger_count is not None
        and details.passenger_count > provider.max_passengers(details.vehicle_category)
    ):
        errors.append(
            f"{details.vehicle_category.value} supports up to "
            f"{provider.max_passengers(details.vehicle_category)} passenger(s)."
        )

    return BookingValidationResponse(
        valid=not missing_fields and not clarifications and not errors,
        missing_fields=missing_fields,
        clarifications=clarifications,
        errors=errors,
    )


def _booking_response(booking: Booking, *, replay: bool = False) -> BookingResponse:
    driver = None
    if booking.driver_id and booking.driver_name and booking.driver_vehicle:
        driver = DriverDetails(
            driver_id=booking.driver_id,
            name=booking.driver_name,
            vehicle=booking.driver_vehicle,
            eta_minutes=booking.driver_eta_minutes or 0,
        )
    return BookingResponse(
        booking_id=booking.booking_id,
        booking_reference=booking.booking_reference,
        status=booking.status,
        passenger_name=booking.passenger_name,
        pickup_location=booking.pickup_location,
        destination=booking.destination,
        vehicle_category=booking.vehicle_category,
        passenger_count=booking.passenger_count,
        payment_preference=booking.payment_preference,
        estimated_fare=booking.estimated_fare_rupees,
        currency=booking.currency,
        payment_confirmed=booking.payment_confirmed,
        driver=driver,
        created_at=booking.created_at,
        idempotent_replay=replay,
    )


def _payment_response(
    payment: Payment,
    booking: Booking,
    *,
    replay: bool = False,
) -> PaymentResponse:
    return PaymentResponse(
        payment_id=payment.payment_id,
        booking_id=payment.booking_id,
        booking_reference=booking.booking_reference,
        status=payment.status,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        created_at=payment.created_at,
        verified_at=payment.verified_at,
        idempotent_replay=replay,
    )


def _booking_request_hash(body: CreateBookingRequest) -> str:
    canonical = json.dumps(
        body.booking_details.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _append_booking_event(
    booking_id: str,
    from_status: BookingStatus | None,
    to_status: BookingStatus,
    actor: str,
    reason: str,
) -> BookingStatusEvent:
    return BookingStatusEvent(
        event_id=str(uuid.uuid4()),
        booking_id=booking_id,
        from_status=from_status.value if from_status else None,
        to_status=to_status.value,
        actor=actor,
        reason=reason,
    )


def _transition_booking(
    booking: Booking,
    to_status: BookingStatus,
    *,
    actor: str,
    reason: str,
) -> BookingStatusEvent:
    current = BookingStatus(booking.status)
    if current == to_status:
        raise ValueError(f"Booking is already {to_status.value}.")
    if to_status not in BOOKING_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_booking_transition",
                "message": f"Cannot move booking from {current.value} to {to_status.value}.",
            },
        )
    booking.status = to_status.value
    booking.updated_at = datetime.now(timezone.utc)
    return _append_booking_event(booking.booking_id, current, to_status, actor, reason)


def _append_payment_event(
    payment_id: str,
    from_status: PaymentStatus | None,
    to_status: PaymentStatus,
    actor: str,
    reason: str,
) -> PaymentStatusEvent:
    return PaymentStatusEvent(
        event_id=str(uuid.uuid4()),
        payment_id=payment_id,
        from_status=from_status.value if from_status else None,
        to_status=to_status.value,
        actor=actor,
        reason=reason,
    )


def _transition_payment(
    payment: Payment,
    to_status: PaymentStatus,
    *,
    actor: str,
    reason: str,
) -> PaymentStatusEvent:
    current = PaymentStatus(payment.status)
    if current == to_status:
        raise ValueError(f"Payment is already {to_status.value}.")
    valid = {
        PaymentStatus.CREATED: {
            PaymentStatus.PENDING,
            PaymentStatus.FAILED,
            PaymentStatus.CANCELLED,
            PaymentStatus.EXPIRED,
        },
        PaymentStatus.PENDING: {
            PaymentStatus.VERIFIED,
            PaymentStatus.FAILED,
            PaymentStatus.CANCELLED,
            PaymentStatus.EXPIRED,
        },
    }
    if to_status not in valid.get(current, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "invalid_payment_transition",
                "message": f"Cannot move payment from {current.value} to {to_status.value}.",
            },
        )
    payment.status = to_status.value
    return _append_payment_event(payment.payment_id, current, to_status, actor, reason)


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    provider: SimulatedRideProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    db = database or Database(resolved_settings.database_url)
    ride_provider = provider or SimulatedRideProvider()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if not resolved_settings.api_key:
            raise RuntimeError("BUSINESS_API_KEY must be configured")
        if resolved_settings.auto_create_schema:
            await db.create_schema()
        await db.initialize()
        yield
        await db.close()

    app = FastAPI(title="Bolo Ride Business API", version="0.2.0", lifespan=lifespan)
    app.state.database = db

    async def require_api_key(request: Request) -> None:
        supplied_key = request.headers.get("X-API-Key")
        if not resolved_settings.api_key or supplied_key is None or not hmac.compare_digest(
            supplied_key, resolved_settings.api_key
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "unauthorized", "message": "Valid server API key required."},
            )

    async def session_dependency():
        async with db.sessions() as session:
            yield session

    auth_dependency = [Depends(require_api_key)]

    def require_simulator() -> None:
        if not resolved_settings.simulator_enabled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "simulator_disabled", "message": "Simulator is disabled."},
            )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/v1/fare-estimates",
        response_model=FareEstimateResponse,
        dependencies=auth_dependency,
    )
    async def estimate_fare(body: FareEstimateRequest) -> FareEstimateResponse:
        return ride_provider.estimate_fare(body)

    @app.post(
        "/v1/bookings/validate",
        response_model=BookingValidationResponse,
        dependencies=auth_dependency,
    )
    async def validate_booking_details(
        body: BookingDraftDetails,
    ) -> BookingValidationResponse:
        return _validate_details(body, ride_provider)

    @app.post(
        "/v1/bookings",
        response_model=BookingResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=auth_dependency,
    )
    async def create_booking(
        body: CreateBookingRequest,
        response: Response,
        session: AsyncSession = Depends(session_dependency),
    ) -> BookingResponse:
        request_hash = _booking_request_hash(body)
        existing = await session.scalar(
            select(Booking).where(Booking.idempotency_key == body.idempotency_key)
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "idempotency_conflict",
                        "message": "This idempotency key was already used with different details.",
                    },
                )
            response.status_code = status.HTTP_200_OK
            return _booking_response(existing, replay=True)

        details = body.booking_details
        validation = _validate_details(BookingDraftDetails(**details.model_dump()), ride_provider)
        if not validation.valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "invalid_booking_details",
                    "validation": validation.model_dump(mode="json"),
                },
            )
        fare_request = FareEstimateRequest(
            pickup=details.pickup_location,
            destination=details.destination,
            vehicle_category=details.vehicle_category,
            passenger_count=details.passenger_count,
        )
        estimate = ride_provider.estimate_fare(fare_request)
        if estimate.status != "estimated" or estimate.fare != details.estimated_fare:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "fare_changed",
                    "message": "Re-estimate and re-confirm the fare before booking.",
                    "current_estimate": estimate.model_dump(mode="json"),
                },
            )

        booking_id = str(uuid.uuid4())
        pickup = ride_provider.resolve_location(details.pickup_location).canonical_name
        destination = ride_provider.resolve_location(details.destination).canonical_name
        booking = Booking(
            booking_id=booking_id,
            booking_reference=f"BR-{booking_id[:8].upper()}",
            idempotency_key=body.idempotency_key,
            request_hash=request_hash,
            status=BookingStatus.CONFIRMED.value,
            passenger_name=details.passenger_name,
            pickup_location=pickup,
            destination=destination,
            vehicle_category=details.vehicle_category.value,
            passenger_count=details.passenger_count,
            payment_preference=(
                details.payment_preference.value if details.payment_preference else None
            ),
            estimated_fare_rupees=estimate.fare,
            currency="INR",
        )
        session.add(booking)
        session.add(
            _append_booking_event(
                booking_id,
                None,
                BookingStatus.CONFIRMED,
                "backend",
                "explicit_passenger_confirmation",
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            duplicate = await session.scalar(
                select(Booking).where(Booking.idempotency_key == body.idempotency_key)
            )
            if duplicate is None:
                logger.exception("booking_persistence_failed")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "code": "booking_persistence_failed",
                        "message": "Retry with the same idempotency key.",
                    },
                )
            if duplicate.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "idempotency_conflict",
                        "message": "This idempotency key was already used with different details.",
                    },
                )
            response.status_code = status.HTTP_200_OK
            return _booking_response(duplicate, replay=True)

        await session.refresh(booking)
        logger.info(
            "booking_created reference=%s status=%s",
            booking.booking_reference,
            booking.status,
        )
        return _booking_response(booking)

    @app.get(
        "/v1/bookings/{booking_id}",
        response_model=BookingResponse,
        dependencies=auth_dependency,
    )
    async def get_booking_status(
        booking_id: str,
        session: AsyncSession = Depends(session_dependency),
    ) -> BookingResponse:
        booking = await session.get(Booking, booking_id)
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "booking_not_found", "message": "Booking was not found."},
            )
        return _booking_response(booking)

    @app.post(
        "/v1/bookings/{booking_id}/cancel",
        response_model=BookingResponse,
        dependencies=auth_dependency,
    )
    async def cancel_booking(
        booking_id: str,
        session: AsyncSession = Depends(session_dependency),
    ) -> BookingResponse:
        booking = await session.get(Booking, booking_id)
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "booking_not_found", "message": "Booking was not found."},
            )
        if booking.status == BookingStatus.CANCELLED.value:
            return _booking_response(booking)
        if booking.payment_confirmed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "payment_verified",
                    "message": "This mock workflow does not refund verified payments; contact support.",
                },
            )
        event = _transition_booking(
            booking,
            BookingStatus.CANCELLED,
            actor="backend",
            reason="passenger_cancellation",
        )
        session.add(event)
        await session.commit()
        await session.refresh(booking)
        logger.info("booking_cancelled reference=%s", booking.booking_reference)
        return _booking_response(booking)

    @app.post(
        "/v1/bookings/{booking_id}/simulate/driver",
        response_model=BookingResponse,
        dependencies=auth_dependency,
    )
    async def simulate_driver_assignment(
        booking_id: str,
        body: DriverSimulationRequest,
        session: AsyncSession = Depends(session_dependency),
    ) -> BookingResponse:
        require_simulator()
        booking = await session.get(Booking, booking_id)
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "booking_not_found", "message": "Booking was not found."},
            )
        target = (
            BookingStatus.DRIVER_ASSIGNED
            if body.outcome == DriverAssignmentOutcome.ASSIGNED
            else BookingStatus.FAILED
        )
        if booking.status == target.value:
            return _booking_response(booking)
        if body.outcome == DriverAssignmentOutcome.ASSIGNED:
            assignment = ride_provider.assign_driver(booking.booking_id)
            booking.driver_id = assignment.driver_id
            booking.driver_name = assignment.name
            booking.driver_vehicle = assignment.vehicle
            booking.driver_eta_minutes = assignment.eta_minutes
        session.add(
            _transition_booking(
                booking,
                target,
                actor="simulated_ride_provider",
                reason=body.outcome.value,
            )
        )
        await session.commit()
        await session.refresh(booking)
        logger.info("booking_status_changed reference=%s status=%s", booking.booking_reference, booking.status)
        return _booking_response(booking)

    @app.post(
        "/v1/bookings/{booking_id}/simulate/complete",
        response_model=BookingResponse,
        dependencies=auth_dependency,
    )
    async def simulate_trip_completion(
        booking_id: str,
        session: AsyncSession = Depends(session_dependency),
    ) -> BookingResponse:
        require_simulator()
        booking = await session.get(Booking, booking_id)
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "booking_not_found", "message": "Booking was not found."},
            )
        if booking.status == BookingStatus.COMPLETED.value:
            return _booking_response(booking)
        session.add(
            _transition_booking(
                booking,
                BookingStatus.COMPLETED,
                actor="simulated_ride_provider",
                reason="simulated_trip_completion",
            )
        )
        await session.commit()
        await session.refresh(booking)
        return _booking_response(booking)

    @app.post(
        "/v1/payment-orders",
        response_model=PaymentResponse,
        status_code=status.HTTP_201_CREATED,
        dependencies=auth_dependency,
    )
    async def create_payment_order(
        body: PaymentOrderRequest,
        response: Response,
        session: AsyncSession = Depends(session_dependency),
    ) -> PaymentResponse:
        booking = await session.get(Booking, body.booking_id)
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "booking_not_found", "message": "Booking was not found."},
            )
        if booking.status not in {
            BookingStatus.CONFIRMED.value,
            BookingStatus.DRIVER_ASSIGNED.value,
            BookingStatus.COMPLETED.value,
        }:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "booking_not_payable",
                    "message": "Payment requires a valid confirmed booking.",
                },
            )
        if booking.payment_confirmed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "already_paid", "message": "Payment is already verified."},
            )

        request_hash = hashlib.sha256(body.booking_id.encode("utf-8")).hexdigest()
        existing_key = await session.scalar(
            select(Payment).where(Payment.idempotency_key == body.idempotency_key)
        )
        if existing_key is not None:
            if existing_key.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "idempotency_conflict",
                        "message": "This idempotency key was used for another payment order.",
                    },
                )
            response.status_code = status.HTTP_200_OK
            return _payment_response(existing_key, booking, replay=True)

        existing_booking = await session.scalar(
            select(Payment).where(Payment.booking_id == body.booking_id)
        )
        if existing_booking is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "payment_order_exists",
                    "message": "A payment order already exists for this booking.",
                    "payment_id": existing_booking.payment_id,
                },
            )

        payment_id = str(uuid.uuid4())
        payment = Payment(
            payment_id=payment_id,
            booking_id=booking.booking_id,
            idempotency_key=body.idempotency_key,
            request_hash=request_hash,
            amount_minor=booking.estimated_fare_rupees * 100,
            currency=booking.currency,
            status=PaymentStatus.CREATED.value,
        )
        session.add(payment)
        session.add(
            _append_payment_event(
                payment_id,
                None,
                PaymentStatus.CREATED,
                "backend",
                "payment_order_created",
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            duplicate = await session.scalar(
                select(Payment).where(Payment.idempotency_key == body.idempotency_key)
            )
            if duplicate is not None and duplicate.request_hash == request_hash:
                response.status_code = status.HTTP_200_OK
                return _payment_response(duplicate, booking, replay=True)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "payment_order_exists",
                    "message": "A payment order already exists for this booking or key.",
                },
            )
        await session.refresh(payment)
        logger.info(
            "payment_order_created reference=%s payment_id=%s amount_minor=%s currency=%s",
            booking.booking_reference,
            payment.payment_id,
            payment.amount_minor,
            payment.currency,
        )
        return _payment_response(payment, booking)

    @app.get(
        "/v1/payments/{payment_id}",
        response_model=PaymentResponse,
        dependencies=auth_dependency,
    )
    async def get_payment_status(
        payment_id: str,
        session: AsyncSession = Depends(session_dependency),
    ) -> PaymentResponse:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "payment_not_found", "message": "Payment was not found."},
            )
        booking = await session.get(Booking, payment.booking_id)
        if booking is None:
            logger.error("payment_booking_missing payment_id=%s", payment_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "payment_integrity_error", "message": "Payment record is incomplete."},
            )
        return _payment_response(payment, booking)

    @app.post(
        "/v1/payments/{payment_id}/simulate-result",
        response_model=PaymentResponse,
        dependencies=auth_dependency,
    )
    async def simulate_payment_result(
        payment_id: str,
        body: PaymentSimulationRequest,
        session: AsyncSession = Depends(session_dependency),
    ) -> PaymentResponse:
        require_simulator()
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "payment_not_found", "message": "Payment was not found."},
            )
        booking = await session.get(Booking, payment.booking_id)
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "payment_integrity_error", "message": "Payment record is incomplete."},
            )

        if payment.mock_outcome is not None:
            if payment.mock_outcome != body.outcome.value:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "payment_result_already_set",
                        "message": "The simulated payment result cannot be changed.",
                    },
                )
            return _payment_response(payment, booking)

        payment.mock_outcome = body.outcome.value
        next_status = {
            MockPaymentOutcome.SUCCESS: PaymentStatus.PENDING,
            MockPaymentOutcome.FAILURE: PaymentStatus.FAILED,
            MockPaymentOutcome.CANCELLED: PaymentStatus.CANCELLED,
            MockPaymentOutcome.EXPIRED: PaymentStatus.EXPIRED,
        }[body.outcome]
        session.add(
            _transition_payment(
                payment,
                next_status,
                actor="mock_payment_gateway",
                reason=f"simulated_{body.outcome.value}",
            )
        )
        await session.commit()
        await session.refresh(payment)
        return _payment_response(payment, booking)

    @app.post(
        "/v1/payments/{payment_id}/verify",
        response_model=PaymentResponse,
        dependencies=auth_dependency,
    )
    async def verify_payment(
        payment_id: str,
        session: AsyncSession = Depends(session_dependency),
    ) -> PaymentResponse:
        payment = await session.get(Payment, payment_id)
        if payment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "payment_not_found", "message": "Payment was not found."},
            )
        booking = await session.get(Booking, payment.booking_id)
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"code": "payment_integrity_error", "message": "Payment record is incomplete."},
            )
        if payment.status == PaymentStatus.VERIFIED.value:
            return _payment_response(payment, booking)
        if payment.status != PaymentStatus.PENDING.value or payment.mock_outcome != MockPaymentOutcome.SUCCESS.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "payment_not_verifiable",
                    "message": "Payment remains unverified until the backend receives a successful mock result.",
                    "payment_status": payment.status,
                },
            )
        expected_amount = booking.estimated_fare_rupees * 100
        if payment.amount_minor != expected_amount or payment.currency != booking.currency:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "payment_amount_mismatch",
                    "message": "Payment amount or currency does not match the confirmed booking.",
                },
            )

        payment.verified_at = datetime.now(timezone.utc)
        booking.payment_confirmed = True
        session.add(
            _transition_payment(
                payment,
                PaymentStatus.VERIFIED,
                actor="backend_verifier",
                reason="mock_gateway_result_verified",
            )
        )
        await session.commit()
        await session.refresh(payment)
        await session.refresh(booking)
        logger.info(
            "payment_verified reference=%s payment_id=%s",
            booking.booking_reference,
            payment.payment_id,
        )
        return _payment_response(payment, booking)

    return app


app = create_app()
