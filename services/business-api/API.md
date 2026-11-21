# Bolo Ride Business API

Base URL: `http://localhost:8010`. All `/v1` endpoints require the server-side
header `X-API-Key: <BUSINESS_API_KEY>`. Do not send this key from browser or
Android code. The web demo uses an allowlisted Next.js route handler to add it
server-side.

The local demo uses deterministic Hyderabad locations, a simulated fare and
driver, and mock payment results. `MOCK_PAYMENTS_ENABLED=true` is required for
the driver/payment simulation operations.

## Booking endpoints

| Method and path | Purpose |
| --- | --- |
| `POST /v1/fare-estimates` | Estimate fare from `pickup`, `destination`, `vehicle_category`, `passenger_count`. |
| `POST /v1/bookings/validate` | Validate a draft; returns missing fields, clarification candidates, and input errors. |
| `POST /v1/bookings` | Create a confirmed booking. Requires `booking_details.booking_confirmation: true` and a 16–128 character `idempotency_key`. |
| `GET /v1/bookings/{booking_id}` | Retrieve backend booking status. |
| `POST /v1/bookings/{booking_id}/cancel` | Cancel an eligible unverified booking. |
| `POST /v1/bookings/{booking_id}/simulate/driver` | Demo-only driver assignment/failure; body uses `{"outcome":"assigned"}` or `{"outcome":"failed"}`. |
| `POST /v1/bookings/{booking_id}/simulate/complete` | Demo-only transition from driver assigned to completed. |

Vehicle categories are `bike`, `auto`, and `sedan`. Passenger count is checked
against simulated capacity. Unknown or ambiguous locations produce a
clarification response rather than an invented fare. The backend re-estimates
the fare at booking time and returns `409` if the fare changed.

Example fare request:

```json
{
  "pickup": "Madhapur",
  "destination": "Gachibowli",
  "vehicle_category": "bike",
  "passenger_count": 1
}
```

Example confirmed booking request:

```json
{
  "booking_details": {
    "passenger_name": "Ananya",
    "pickup_location": "Madhapur",
    "destination": "Gachibowli",
    "vehicle_category": "bike",
    "passenger_count": 1,
    "payment_preference": "upi",
    "estimated_fare": 120,
    "booking_confirmation": true
  },
  "idempotency_key": "client-generated-unique-key"
}
```

## Mock payment endpoints

| Method and path | Purpose |
| --- | --- |
| `POST /v1/payment-orders` | Create one payment order for a valid booking; amount and currency come from the backend booking. Requires an idempotency key. |
| `GET /v1/payments/{payment_id}` | Retrieve payment status. |
| `POST /v1/payments/{payment_id}/simulate-result` | Demo/test-only mock gateway result; body outcome is `success`, `failure`, `cancelled`, or `expired`. |
| `POST /v1/payments/{payment_id}/verify` | Verify a pending successful mock result and mark the payment and booking as verified. |

A successful simulated result advances payment to `PENDING`, not `VERIFIED`.
Only `POST .../verify` can mark payment `VERIFIED` and set
`booking.payment_confirmed=true`. Do not report payment success from frontend
state, a voice transcript, or an LLM response.

The backend rejects unknown fields, invalid transitions, duplicate or
conflicting idempotency keys, amount/currency mismatches, and payment for
cancelled/failed bookings. HTTP errors preserve the backend status and
structured `detail` response.

## Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Yes | PostgreSQL async SQLAlchemy URL; compose sets the container URL. |
| `BUSINESS_API_KEY` | Yes | Long random server-only secret, sent as `X-API-Key`. |
| `MOCK_PAYMENTS_ENABLED` | For demo simulations | Set `true` only for local/test demo environments. |
| `BUSINESS_API_URL` | For web proxy | Internal URL to this API; server-side only, e.g. `http://business-api:8010`. |

Run `alembic upgrade head` before starting the API outside the Compose demo.
Tests currently use SQLite and do not substitute for a live PostgreSQL test.
