# Bolo Ride Business API

This isolated FastAPI service owns fare estimates, booking validation, booking
records, status, and cancellation. The Agora voice service calls it server to
server. Browser requests go through the Next.js server-side proxy, which keeps
`BUSINESS_API_KEY` out of the browser.

The initial `SimulatedRideProvider` uses a deterministic Hyderabad locality and
fare table. `Madhapur` to `Gachibowli` by bike estimates to ₹120. Unrecognized or
ambiguous locations return structured clarification results rather than guessed
coordinates or fares. Replace the simulator only after a real ride-provider
contract is selected.

## Run a watchable demo

On Windows, run `.\scripts\demo.ps1` from the repository root after installing
the API and web dependencies. It starts the API with a local SQLite file and
the Next.js demo; press Ctrl+C in that terminal to stop both services.

If Docker Desktop is available, `docker compose --env-file .env.example -f
docker-compose.demo.yml up --build` starts PostgreSQL, applies Alembic
migrations, starts this API, and launches the same web demo. The local-only
default API key is for demo use; set a unique `BUSINESS_API_KEY` before
exposing any service outside localhost.

The API is also available at [http://localhost:8010/docs](http://localhost:8010/docs).
Every business endpoint requires the server-side `X-API-Key` header.

For manual API development, copy `.env.example` to `.env`, configure a PostgreSQL
`DATABASE_URL` and a strong `BUSINESS_API_KEY`, then run:

```powershell
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

`POST /v1/bookings` requires the backend fare and explicit
`booking_confirmation: true`; it revalidates the fare before persisting.
Database constraints and request hashes enforce idempotency.

## API lifecycle

- `POST /v1/fare-estimates` and `POST /v1/bookings/validate` validate trip inputs.
- `POST /v1/bookings` creates a confirmed booking only after explicit confirmation.
- `GET /v1/bookings/{booking_id}` returns backend booking status.
- `POST /v1/bookings/{booking_id}/cancel` cancels an eligible booking.
- `POST /v1/bookings/{booking_id}/simulate/driver` and
  `/simulate/complete` advance the simulated ride.
- `POST /v1/payment-orders` creates an amount-bound payment order.
- `GET /v1/payments/{payment_id}` retrieves its status.
- `POST /v1/payments/{payment_id}/simulate-result` submits a mock gateway result.
- `POST /v1/payments/{payment_id}/verify` is the only operation that can mark a
  successful mock payment `VERIFIED` and update its booking.

The mock simulation routes are available only when `MOCK_PAYMENTS_ENABLED=true`.
Do not expose them as LLM tools. Never ask for a PIN, OTP or banking credentials.

## Validation

The integration tests use SQLite and the deterministic simulator. They verify
API contracts and persistence behavior, but do not validate a live PostgreSQL
deployment or an external ride provider.
