from __future__ import annotations

import sqlite3

import pytest


HEADERS = {"X-API-Key": "test-business-key"}


def booking_details(**overrides):
    details = {
        "passenger_name": "Asha",
        "pickup_location": "Madhapur",
        "destination": "Gachibowli",
        "vehicle_category": "bike",
        "passenger_count": 1,
        "payment_preference": None,
        "estimated_fare": 120,
        "booking_confirmation": True,
    }
    details.update(overrides)
    return details


def create_booking(client, *, key="booking-attempt-00000001", **details):
    response = client.post(
        "/v1/bookings",
        headers=HEADERS,
        json={
            "booking_details": booking_details(**details),
            "idempotency_key": key,
        },
    )
    return response


def create_payment(client, booking_id, key="payment-attempt-00000001"):
    return client.post(
        "/v1/payment-orders",
        headers=HEADERS,
        json={"booking_id": booking_id, "idempotency_key": key},
    )


def test_fare_estimate_validates_capacity_and_ambiguous_locations(client):
    estimate = client.post(
        "/v1/fare-estimates",
        headers=HEADERS,
        json={
            "pickup": "Madhapur",
            "destination": "Gachibowli",
            "vehicle_category": "bike",
            "passenger_count": 1,
        },
    )
    assert estimate.status_code == 200
    assert estimate.json()["status"] == "estimated"
    assert estimate.json()["fare"] == 120
    assert estimate.json()["currency"] == "INR"

    ambiguous = client.post(
        "/v1/fare-estimates",
        headers=HEADERS,
        json={
            "pickup": "Railway Station",
            "destination": "Gachibowli",
            "vehicle_category": "bike",
            "passenger_count": 1,
        },
    )
    assert ambiguous.status_code == 200
    assert ambiguous.json()["status"] == "needs_clarification"
    assert ambiguous.json()["clarifications"]["pickup"] == [
        "Secunderabad Railway Station",
        "Hyderabad Deccan (Nampally) Railway Station",
    ]

    too_many = client.post(
        "/v1/fare-estimates",
        headers=HEADERS,
        json={
            "pickup": "Madhapur",
            "destination": "Gachibowli",
            "vehicle_category": "bike",
            "passenger_count": 2,
        },
    )
    assert too_many.status_code == 200
    assert too_many.json()["status"] == "needs_clarification"
    assert "passenger_count" in too_many.json()["clarifications"]


def test_validate_booking_reports_missing_fields_and_ambiguity(client):
    response = client.post(
        "/v1/bookings/validate",
        headers=HEADERS,
        json={"pickup_location": "Railway Station"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["missing_fields"] == [
        "destination",
        "vehicle_category",
        "passenger_count",
    ]
    assert "pickup_location" in body["clarifications"]


def test_creation_requires_confirmation_and_rechecks_backend_fare(client):
    not_confirmed = booking_details(booking_confirmation=False)
    response = client.post(
        "/v1/bookings",
        headers=HEADERS,
        json={"booking_details": not_confirmed, "idempotency_key": "draft-key-00000001"},
    )
    assert response.status_code == 422

    changed_fare = booking_details(estimated_fare=119)
    response = client.post(
        "/v1/bookings",
        headers=HEADERS,
        json={"booking_details": changed_fare, "idempotency_key": "draft-key-00000002"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "fare_changed"


def test_booking_lifecycle_driver_assignment_completion_and_event_log(client):
    created = create_booking(client)
    assert created.status_code == 201
    data = created.json()
    assert data["status"] == "CONFIRMED"
    assert data["booking_reference"].startswith("BR-")
    assert data["payment_confirmed"] is False
    booking_id = data["booking_id"]

    assigned = client.post(
        f"/v1/bookings/{booking_id}/simulate/driver",
        headers=HEADERS,
        json={"outcome": "assigned"},
    )
    assert assigned.status_code == 200
    assert assigned.json()["status"] == "DRIVER_ASSIGNED"
    assert assigned.json()["driver"]["simulated"] is True
    assert assigned.json()["driver"]["eta_minutes"] == 7

    completed = client.post(
        f"/v1/bookings/{booking_id}/simulate/complete",
        headers=HEADERS,
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETED"
    assert client.post(f"/v1/bookings/{booking_id}/cancel", headers=HEADERS).status_code == 409

    with sqlite3.connect(client.database_path) as connection:
        states = connection.execute(
            "SELECT to_status FROM booking_status_events WHERE booking_id = ? ORDER BY rowid",
            (booking_id,),
        ).fetchall()
    assert [row[0] for row in states] == ["CONFIRMED", "DRIVER_ASSIGNED", "COMPLETED"]


def test_booking_cancel_and_duplicate_creation_are_idempotent(client):
    request = {
        "booking_details": booking_details(),
        "idempotency_key": "booking-attempt-00000002",
    }
    first = client.post("/v1/bookings", headers=HEADERS, json=request)
    assert first.status_code == 201
    replay = client.post("/v1/bookings", headers=HEADERS, json=request)
    assert replay.status_code == 200
    assert replay.json()["booking_id"] == first.json()["booking_id"]
    assert replay.json()["idempotent_replay"] is True

    conflict = client.post(
        "/v1/bookings",
        headers=HEADERS,
        json={
            "booking_details": booking_details(destination="Hitech City"),
            "idempotency_key": "booking-attempt-00000002",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"

    booking_id = first.json()["booking_id"]
    cancelled = client.post(f"/v1/bookings/{booking_id}/cancel", headers=HEADERS)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert client.post(f"/v1/bookings/{booking_id}/cancel", headers=HEADERS).json()[
        "status"
    ] == "CANCELLED"


def test_driver_failure_is_a_terminal_booking_status(client):
    booking = create_booking(client, key="booking-attempt-00000003").json()
    failed = client.post(
        f"/v1/bookings/{booking['booking_id']}/simulate/driver",
        headers=HEADERS,
        json={"outcome": "failed"},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "FAILED"
    assert client.post(
        f"/v1/bookings/{booking['booking_id']}/cancel",
        headers=HEADERS,
    ).status_code == 409


def test_payment_order_is_unique_and_backend_verified(client):
    booking = create_booking(client, key="booking-attempt-00000004").json()
    payment_response = create_payment(client, booking["booking_id"])
    assert payment_response.status_code == 201
    payment = payment_response.json()
    assert payment["status"] == "CREATED"
    assert payment["amount_minor"] == 12000
    assert payment["currency"] == "INR"

    replay = create_payment(client, booking["booking_id"])
    assert replay.status_code == 200
    assert replay.json()["payment_id"] == payment["payment_id"]

    duplicate_order = create_payment(
        client,
        booking["booking_id"],
        key="payment-attempt-00000002",
    )
    assert duplicate_order.status_code == 409

    unverified = client.post(
        f"/v1/payments/{payment['payment_id']}/verify",
        headers=HEADERS,
    )
    assert unverified.status_code == 409
    assert unverified.json()["detail"]["code"] == "payment_not_verifiable"
    assert client.get(
        f"/v1/bookings/{booking['booking_id']}",
        headers=HEADERS,
    ).json()["payment_confirmed"] is False

    pending = client.post(
        f"/v1/payments/{payment['payment_id']}/simulate-result",
        headers=HEADERS,
        json={"outcome": "success"},
    )
    assert pending.status_code == 200
    assert pending.json()["status"] == "PENDING"

    verified = client.post(
        f"/v1/payments/{payment['payment_id']}/verify",
        headers=HEADERS,
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "VERIFIED"
    assert client.get(
        f"/v1/bookings/{booking['booking_id']}",
        headers=HEADERS,
    ).json()["payment_confirmed"] is True


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        ("failure", "FAILED"),
        ("cancelled", "CANCELLED"),
        ("expired", "EXPIRED"),
    ],
)
def test_payment_failure_cancel_and_expiry_remain_unverified(
    client,
    outcome,
    expected_status,
):
    booking = create_booking(client, key=f"booking-{outcome}-000000001").json()
    payment = create_payment(
        client,
        booking["booking_id"],
        key=f"payment-{outcome}-000000001",
    ).json()
    response = client.post(
        f"/v1/payments/{payment['payment_id']}/simulate-result",
        headers=HEADERS,
        json={"outcome": outcome},
    )
    assert response.status_code == 200
    assert response.json()["status"] == expected_status
    assert client.post(
        f"/v1/payments/{payment['payment_id']}/verify",
        headers=HEADERS,
    ).status_code == 409
    assert client.get(
        f"/v1/bookings/{booking['booking_id']}",
        headers=HEADERS,
    ).json()["payment_confirmed"] is False


def test_payment_verification_checks_backend_amount_and_currency(client):
    booking = create_booking(client, key="booking-amount-00000001").json()
    payment = create_payment(
        client,
        booking["booking_id"],
        key="payment-amount-00000001",
    ).json()
    client.post(
        f"/v1/payments/{payment['payment_id']}/simulate-result",
        headers=HEADERS,
        json={"outcome": "success"},
    )

    with sqlite3.connect(client.database_path) as connection:
        connection.execute(
            "UPDATE payments SET amount_minor = 1 WHERE payment_id = ?",
            (payment["payment_id"],),
        )
        connection.commit()

    response = client.post(
        f"/v1/payments/{payment['payment_id']}/verify",
        headers=HEADERS,
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "payment_amount_mismatch"
    assert client.get(
        f"/v1/bookings/{booking['booking_id']}",
        headers=HEADERS,
    ).json()["payment_confirmed"] is False


def test_payment_schema_rejects_sensitive_credentials_and_server_api_requires_key(client):
    unauthenticated = client.post(
        "/v1/fare-estimates",
        json={
            "pickup": "Madhapur",
            "destination": "Gachibowli",
            "vehicle_category": "bike",
            "passenger_count": 1,
        },
    )
    assert unauthenticated.status_code == 401

    booking = create_booking(client, key="booking-pin-00000000001").json()
    response = client.post(
        "/v1/payment-orders",
        headers=HEADERS,
        json={
            "booking_id": booking["booking_id"],
            "idempotency_key": "payment-pin-00000001",
            "upi_pin": "1234",
        },
    )
    assert response.status_code == 422


def test_payment_simulator_is_disabled_when_not_configured(tmp_path):
    from fastapi.testclient import TestClient

    from app.database import Database
    from app.main import Settings, create_app

    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'disabled.sqlite3'}")
    app = create_app(
        Settings(
            database_url="",
            api_key="test-business-key",
            simulator_enabled=False,
            auto_create_schema=True,
        ),
        database=database,
    )
    with TestClient(app) as disabled_client:
        response = disabled_client.post(
            "/v1/payments/not-a-payment/simulate-result",
            headers=HEADERS,
            json={"outcome": "success"},
        )
    assert response.status_code == 404
