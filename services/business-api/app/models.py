from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('CONFIRMED', 'DRIVER_ASSIGNED', 'COMPLETED', 'CANCELLED', 'FAILED')",
            name="ck_bookings_status",
        ),
    )

    booking_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    booking_reference: Mapped[str] = mapped_column(String(24), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="CONFIRMED")
    passenger_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pickup_location: Mapped[str] = mapped_column(String(200))
    destination: Mapped[str] = mapped_column(String(200))
    vehicle_category: Mapped[str] = mapped_column(String(16))
    passenger_count: Mapped[int] = mapped_column(Integer)
    payment_preference: Mapped[str | None] = mapped_column(String(16), nullable=True)
    estimated_fare_rupees: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    payment_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    driver_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    driver_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    driver_vehicle: Mapped[str | None] = mapped_column(String(80), nullable=True)
    driver_eta_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    status_events: Mapped[list[BookingStatusEvent]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="BookingStatusEvent.created_at",
    )
    payment: Mapped[Payment | None] = relationship(
        back_populates="booking",
        uselist=False,
        cascade="all, delete-orphan",
    )


class BookingStatusEvent(Base):
    __tablename__ = "booking_status_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    booking_id: Mapped[str] = mapped_column(
        ForeignKey("bookings.booking_id", ondelete="CASCADE"),
        index=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    booking: Mapped[Booking] = relationship(back_populates="status_events")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_payments_booking_id"),
        CheckConstraint(
            "status IN ('CREATED', 'PENDING', 'VERIFIED', 'FAILED', 'CANCELLED', 'EXPIRED')",
            name="ck_payments_status",
        ),
    )

    payment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    booking_id: Mapped[str] = mapped_column(
        ForeignKey("bookings.booking_id", ondelete="RESTRICT"),
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), default="CREATED")
    mock_outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    booking: Mapped[Booking] = relationship(back_populates="payment")
    status_events: Mapped[list[PaymentStatusEvent]] = relationship(
        back_populates="payment",
        cascade="all, delete-orphan",
        order_by="PaymentStatusEvent.created_at",
    )


class PaymentStatusEvent(Base):
    __tablename__ = "payment_status_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    payment_id: Mapped[str] = mapped_column(
        ForeignKey("payments.payment_id", ondelete="CASCADE"),
        index=True,
    )
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    payment: Mapped[Payment] = relationship(back_populates="status_events")
