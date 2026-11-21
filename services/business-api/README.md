# Bolo Ride Business API

This isolated FastAPI service owns fare estimates, booking validation, booking
records, status, and cancellation. The Agora voice service calls it server to
server; it is not exposed to the browser or Android client.

The initial `SimulatedRideProvider` uses a deterministic Hyderabad locality and
fare table. `Madhapur` to `Gachibowli` by bike estimates to ₹120. Unrecognized or
ambiguous locations return structured clarification results rather than guessed
coordinates or fares. Replace the simulator only after a real ride-provider
contract is selected.

## Run locally

1. Copy `.env.example` to `.env` and set a PostgreSQL `DATABASE_URL` and a long,
   random `BUSINESS_API_KEY`.
2. Install `requirements.txt`.
3. Run `uvicorn app.main:app --host 127.0.0.1 --port 8010`.

The API uses `X-API-Key` authentication on all business endpoints. Keep the key
only in server environment variables. `POST /v1/bookings` requires the fare
returned by the backend and `booking_confirmation: true`; it revalidates the
fare before persisting. A unique database constraint and request hash enforce
idempotency across service processes.

`Base.metadata.create_all` initializes this prototype database. Production
rollouts should introduce versioned migrations before schema changes.

## Validation

The integration tests use SQLite and the deterministic simulator. They verify
API contracts and persistence behavior, but do not validate a live PostgreSQL
deployment or an external ride provider.
