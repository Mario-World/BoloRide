# 08 Security

> Trust boundaries, secret handling, and security-relevant invariants for the two-process Python quickstart.

## Trust Model

- The browser is untrusted. It may see Agora tokens and opaque, short-lived session tickets issued by FastAPI.
- The FastAPI server is the only process that holds `AGORA_APP_CERTIFICATE` and any future BYOK keys.
- The Next.js process sees `AGENT_BACKEND_URL` (a server-side build env var) but does not see any Agora secret.
- The FastAPI API has no per-user authentication today. CORS is not an authentication boundary and session tickets are bearer capabilities, not user identity.

## Environment Variable Boundaries

| Boundary       | Variables                                                              |
| -------------- | ---------------------------------------------------------------------- |
| Browser        | Agora session token and opaque session ticket (runtime capabilities)   |
| Next build/run | `AGENT_BACKEND_URL`                                                    |
| FastAPI        | `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `PORT`, `AGENT_ALLOWED_ORIGINS` |

Mark `AGORA_APP_CERTIFICATE` as a sensitive secret in whichever host runs the Python service. The certificate value never appears in `web/`.

## Token Issuance

- `server.py` `get_config` calls `generate_convo_ai_token(GenerateConvoAITokenOptions(..., token_expire=3600))`.
- The same token grants RTC and RTM privileges for a random server-generated non-zero UID.
- Sessions also carry `expires_in=3600` in `create_async_session`, so an idle session aligns with token expiry.
- A separate HMAC-SHA256 session ticket is signed with a domain-separated key derived from the App Certificate; it does not expose the certificate.
- Renewal, agent start, and agent stop require the ticket and matching channel/UID claims. Start returns a ticket bound to the returned agent ID.

## Token Renewal

- The client listens for `token-privilege-will-expire` on the RTC engine.
- It calls `getConfig()` once with the channel, UID, and session ticket, then renews RTC and RTM with the returned token.
- If renewal fails, the next failure surfaces through `MESSAGE_ERROR` on RTM or RTC disconnect events.

## CORS

`server/src/server.py` uses `AGENT_ALLOWED_ORIGINS`, defaults to local web
development origins, and disables credentialed CORS. Configure the deployed web
origin explicitly. CORS only constrains browsers; it does not authorize requests.

## Authentication

- No user authentication middleware on FastAPI routes.
- No auth in the Next.js rewrites; the browser hits the rewrite directly.
- The initial `/get_config` request is unauthenticated; anyone who can reach the API can create a session.
- The signed ticket limits subsequent actions to the issued session but is a bearer capability; anyone who obtains it can use it until expiry.

If you need real auth, add a FastAPI dependency that validates a header on each route. Update `web/src/services/api.ts` and `verify-api-contracts.ts` to send and assert the header.

## Input Validation

- pydantic `StartAgentRequest` / `StopAgentRequest` validate body shape automatically.
- Request models validate their required fields. Ticket verification checks signature, expiry, subject, and matching session identity before token renewal and lifecycle operations.
- Internal provider exceptions are logged and returned as sanitized `500` details; client errors must not include credential values.

## Secret Handling Rules

- `server/.env` is the developer's secret store; do not commit it.
- `server/.env.example` documents shape only — never put real values there.
- `load_dotenv` reads `server/.env` using a path derived from `server/src/server.py`, without overriding host environment values; missing credentials fail startup initialization and leave routes returning `500`.
- Do not log full env. `logger.error("failed: %s", err)` is fine; `logger.error(os.environ)` is not.

## CSP / Security Headers

- No CSP or HSTS headers are set on FastAPI responses today.
- No security headers are configured in `web/next.config.ts`.
- Add them at the reverse-proxy layer if you put one in front of FastAPI.

## Known Limitations

- No user authentication or rate limiting on `/get_config`, `/startAgent`, `/stopAgent`. A determined client can rapidly issue tokens or create sessions — add these before public exposure.
- `server/scripts/run_fake_server.py` accepts the same routes with no validation. Do not deploy it.
- Ticket and active-session state are process-local; multi-worker deployments do not share idempotency state or sessions.
- The web client does not encrypt the browser → Next → FastAPI path beyond TLS at the host level.

## Related Deep Dives

- [Managed Agent Config](L2/managed_agent_config.md) — Where to plug BYOK vendor keys.
