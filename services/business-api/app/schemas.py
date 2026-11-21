from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VehicleCategory(str, Enum):
    BIKE = "bike"
    AUTO = "auto"
    SEDAN = "sedan"


class PaymentPreference(str, Enum):
    CASH = "cash"
    UPI = "upi"
    CARD = "card"


class BookingStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    DRIVER_ASSIGNED = "DRIVER_ASSIGNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class PaymentStatus(str, Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class MockPaymentOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class DriverAssignmentOutcome(str, Enum):
    ASSIGNED = "assigned"
    FAILED = "failed"


class BookingDraftDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    passenger_name: str | None = Field(default=None, min_length=1, max_length=120)
    pickup_location: str | None = Field(default=None, min_length=2, max_length=200)
    destination: str | None = Field(default=None, min_length=2, max_length=200)
    vehicle_category: VehicleCategory | None = None
    passenger_count: int | None = Field(default=None, ge=1, le=6)
    payment_preference: PaymentPreference | None = None
    estimated_fare: int | None = Field(default=None, ge=1, le=100_000)
    booking_confirmation: bool = False


class FareEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pickup: str = Field(min_length=2, max_length=200)
    destination: str = Field(min_length=2, max_length=200)
    vehicle_category: VehicleCategory
    passenger_count: int = Field(ge=1, le=6)


class FareEstimateResponse(BaseModel):
    status: Literal["estimated", "needs_clarification"]
    fare: int | None
    currency: Literal["INR"] = "INR"
    distance_km: float | None = None
    provider: Literal["simulated"] = "simulated"
    clarifications: dict[str, list[str]] = Field(default_factory=dict)


class BookingValidationResponse(BaseModel):
    valid: bool
    missing_fields: list[str] = Field(default_factory=list)
    clarifications: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class ConfirmedBookingDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    passenger_name: str | None = Field(default=None, min_length=1, max_length=120)
    pickup_location: str = Field(min_length=2, max_length=200)
    destination: str = Field(min_length=2, max_length=200)
    vehicle_category: VehicleCategory
    passenger_count: int = Field(ge=1, le=6)
    payment_preference: PaymentPreference | None = None
    estimated_fare: int = Field(ge=1, le=100_000)
    booking_confirmation: Literal[True]


class CreateBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booking_details: ConfirmedBookingDetails
    idempotency_key: str = Field(min_length=16, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def strip_idempotency_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("idempotency_key must not be blank")
        return normalized


class DriverDetails(BaseModel):
    driver_id: str
    name: str
    vehicle: str
    eta_minutes: int
    simulated: Literal[True] = True


class BookingResponse(BaseModel):
    booking_id: str
    booking_reference: str
    status: BookingStatus
    passenger_name: str | None
    pickup_location: str
    destination: str
    vehicle_category: VehicleCategory
    passenger_count: int
    payment_preference: PaymentPreference | None
    estimated_fare: int
    currency: Literal["INR"] = "INR"
    payment_confirmed: bool
    driver: DriverDetails | None = None
    created_at: datetime
    idempotent_replay: bool = False


class PaymentOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booking_id: str = Field(min_length=36, max_length=36)
    idempotency_key: str = Field(min_length=16, max_length=128)

    @field_validator("idempotency_key")
    @classmethod
    def strip_idempotency_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("idempotency_key must not be blank")
        return normalized


class PaymentSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: MockPaymentOutcome


class DriverSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: DriverAssignmentOutcome


class PaymentResponse(BaseModel):
    payment_id: str
    booking_id: str
    booking_reference: str
    status: PaymentStatus
    amount_minor: int
    currency: Literal["INR"] = "INR"
    created_at: datetime
    verified_at: datetime | None = None
    idempotent_replay: bool = False
