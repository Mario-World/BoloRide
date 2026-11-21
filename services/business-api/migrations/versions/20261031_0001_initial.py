"""Create booking and mock payment tables.

Revision ID: 20261031_0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20261031_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("booking_id", sa.String(length=36), primary_key=True),
        sa.Column("booking_reference", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("passenger_name", sa.String(length=120), nullable=True),
        sa.Column("pickup_location", sa.String(length=200), nullable=False),
        sa.Column("destination", sa.String(length=200), nullable=False),
        sa.Column("vehicle_category", sa.String(length=16), nullable=False),
        sa.Column("passenger_count", sa.Integer(), nullable=False),
        sa.Column("payment_preference", sa.String(length=16), nullable=True),
        sa.Column("estimated_fare_rupees", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_confirmed", sa.Boolean(), nullable=False),
        sa.Column("driver_id", sa.String(length=36), nullable=True),
        sa.Column("driver_name", sa.String(length=120), nullable=True),
        sa.Column("driver_vehicle", sa.String(length=80), nullable=True),
        sa.Column("driver_eta_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('CONFIRMED', 'DRIVER_ASSIGNED', 'COMPLETED', 'CANCELLED', 'FAILED')",
            name="ck_bookings_status",
        ),
        sa.UniqueConstraint("booking_reference", name="uq_bookings_booking_reference"),
        sa.UniqueConstraint("idempotency_key", name="uq_bookings_idempotency_key"),
    )
    op.create_index("ix_bookings_booking_reference", "bookings", ["booking_reference"])
    op.create_index("ix_bookings_idempotency_key", "bookings", ["idempotency_key"])

    op.create_table(
        "booking_status_events",
        sa.Column("event_id", sa.String(length=36), primary_key=True),
        sa.Column("booking_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.booking_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_booking_status_events_booking_id", "booking_status_events", ["booking_id"])

    op.create_table(
        "payments",
        sa.Column("payment_id", sa.String(length=36), primary_key=True),
        sa.Column("booking_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("mock_outcome", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('CREATED', 'PENDING', 'VERIFIED', 'FAILED', 'CANCELLED', 'EXPIRED')",
            name="ck_payments_status",
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.booking_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("booking_id", name="uq_payments_booking_id"),
        sa.UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
    )
    op.create_index("ix_payments_booking_id", "payments", ["booking_id"])
    op.create_index("ix_payments_idempotency_key", "payments", ["idempotency_key"])

    op.create_table(
        "payment_status_events",
        sa.Column("event_id", sa.String(length=36), primary_key=True),
        sa.Column("payment_id", sa.String(length=36), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=False),
        sa.Column("actor", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.payment_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_payment_status_events_payment_id", "payment_status_events", ["payment_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_status_events_payment_id", table_name="payment_status_events")
    op.drop_table("payment_status_events")
    op.drop_index("ix_payments_idempotency_key", table_name="payments")
    op.drop_index("ix_payments_booking_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_booking_status_events_booking_id", table_name="booking_status_events")
    op.drop_table("booking_status_events")
    op.drop_index("ix_bookings_idempotency_key", table_name="bookings")
    op.drop_index("ix_bookings_booking_reference", table_name="bookings")
    op.drop_table("bookings")
