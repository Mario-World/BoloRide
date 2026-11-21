# Bolo Ride Development Roadmap

This is a milestone plan, not an implementation. The current workspace contains
two separate Agora voice quickstarts and no ride-booking business backend.
Large code migrations and business-feature implementation require approval.

## Milestones

### 0. Approve the project baseline

- Decide how the untracked `bolo-ride-voice/` web/Python quickstart and the
  tracked Android/Python quickstart will be consolidated or retained.
- Review local `.env` files and Agora metadata before staging anything.
- Define the one canonical development, test, and deployment workflow.

**Exit criteria:** approved repository layout; no credentials included; existing
Android and web implementations are preserved until parity is established.

### 1. Define business contracts and persistence

- Agree on the minimum rider, fare quote, booking, payment, and operation
  concepts before choosing concrete schemas or routes.
- Add PostgreSQL configuration, migrations, and repository/service boundaries
  in the business API.
- Keep the voice-agent service out of direct database access.

**Exit criteria:** migrations run from a clean database; business model tests
cover valid and invalid state transitions.

### 2. Add deterministic fare and ride-provider simulation

- Add a mock ride-provider adapter and deterministic fare estimation.
- Make fare inputs, currency, rounding, unavailable routes, and quote expiry
  explicit in the API contract.
- Keep provider-specific behavior behind the business service.

**Exit criteria:** repeatable tests for fare estimates and provider failures;
the voice agent cannot create or mutate bookings through this milestone.

### 3. Implement confirmed, idempotent booking

- Model booking as a server-owned state machine.
- Collect and normalize ride details, present a read-back/quote, and require
  explicit rider confirmation before a create operation.
- Persist an idempotency key per logical rider action, scoped to rider and
  operation and bound to normalized inputs; reject mismatched key reuse.
- Reconcile ambiguous timeouts against the business record/provider before
  retrying.

**Exit criteria:** tests prove no booking is created before confirmation,
duplicate requests do not create duplicate bookings, and uncertain outcomes
are never reported as confirmed.

### 4. Add mock payments and verified status

- Add a mock payment provider behind the business API.
- Persist payment intent and provider references; verify status server-side.
- Define safe behavior for timeouts, retries, and mismatched provider/database
  state. Never request UPI PINs or OTPs.

**Exit criteria:** tests cover success, decline, duplicate request, timeout,
reconciliation, and payment/booking state mismatch.

### 5. Connect Agora tools to business operations

- Add a server-to-server tool adapter from the voice-agent service to the
  authenticated business API.
- Use typed tool arguments and structured business results, including an
  explicit unknown/pending outcome.
- Keep the Agora App Certificate and all provider credentials server-only.

**Exit criteria:** contract tests show that the agent can only invoke approved
business operations; server validation and confirmation rules hold even when
the model produces malformed or repeated arguments.

### 6. Deliver multilingual web voice UX

- Adapt the existing Next.js voice prototype after the repository baseline is
  approved.
- Validate ASR, LLM, and TTS support for Telugu, Hindi, Kannada, and English;
  test language selection, code-switching, clarifications, and fallbacks.
- Add fare read-back and explicit confirmation UI before calling the booking
  operation.

**Exit criteria:** end-to-end tests for every supported language and booking
state; no unverified booking/payment claims in the UI or spoken response.

### 7. Build the future Android client

- Reuse the existing Kotlin/Compose voice demo as a reference, not as a second
  business implementation.
- Consume the same approved API contracts and business-service authorization
  as the web app.
- Preserve Agora session lifecycle, interruption, microphone cleanup, and
  token renewal behavior.

**Exit criteria:** Android flows pass the same booking/payment invariants and
voice-session tests as the web client.

### 8. Production hardening

- Add product authentication/authorization, rate limits, privacy controls,
  observability, and deployment configuration.
- Review CORS, secret handling, data retention, and audit requirements.
- Exercise concurrency, provider timeouts, retries, and recovery in staging.

**Exit criteria:** operational runbooks and security review are complete before
any public production deployment.

## Files Recommended

| Timing | Files or areas | Purpose |
| --- | --- | --- |
| This documentation pass | `README.md`, `ARCHITECTURE.md`, `ROADMAP.md` | Explain current state, target boundaries, and staged plan. |
| After baseline approval | `services/business-api/app/`, `services/business-api/migrations/`, `infra/postgres/` | Add business API, persistence, and local PostgreSQL support without mixing it into Agora lifecycle code. |
| After domain contracts are approved | `packages/contracts/` and business API tests | Keep web, voice tools, and future Android aligned to typed contracts. |
| After business APIs are tested | `services/voice-agent/` tool adapters and tests | Connect Agora tool calls to authorized server-side operations. |
| After contracts stabilize | `apps/web/` booking UI, API client, and tests | Add fare read-back, confirmation, and multilingual voice UX. |
| Future native phase | `apps/android/` or the existing root `app/` | Build a native client against the shared contracts. |

The existing root `server/app/` and nested `bolo-ride-voice/server/src/` should
not both become business APIs. Choose and document the canonical voice-agent
implementation before moving or deleting either.
