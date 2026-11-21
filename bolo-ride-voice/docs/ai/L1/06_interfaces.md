# 06 Interfaces

> Boundary contracts: FastAPI routes, Next rewrites, environment variables, and managed agent payload.

## Python Backend Routes

`server/src/server.py` registers these on an `APIRouter`:

| Path           | Method | Request                                                                              | Success (200)                                                                                | Errors                                                          |
| -------------- | ------ | ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `/get_config`  | GET    | New session: no query. Renewal: `channel`, `uid`, `session_ticket`                   | `{ "code": 0, "msg": "success", "data": { app_id, token, uid, channel_name, agent_uid, session_ticket } }` | `401` invalid/expired ticket; `403` session mismatch; `500` config/provider errors |
| `/startAgent`  | POST   | JSON `StartAgentRequest`: `channelName`, `rtcUid`, `userUid`, `sessionTicket`, `language` (`en`, `hi`, `kn`, `te`, default `en`), optional `parameters` | `{ "code": 0, "msg": "success", "data": { agent_id, channel_name, status, session_ticket } }` | `400` validation; `401` invalid/expired ticket; `403` mismatch; `409` language/session conflict; `503` missing speech-provider configuration; `500` runtime |
| `/stopAgent`   | POST   | JSON `StopAgentRequest`: `agentId`, `channelName`, `userUid`, `sessionTicket`       | `{ "code": 0, "msg": "success" }`                                                            | `401` invalid/expired ticket; `403` mismatch; `500` runtime      |

CORS middleware uses comma-separated `AGENT_ALLOWED_ORIGINS`; credentials are disabled.

`StartAgentRequest.language` selects the response language and TTS locale for
the session. The same language must be used for idempotent start retries.
`parameters` is optional and carries `output_audio_codec`.

`get_config` creates a random channel, non-zero user UID, agent UID, and signed expiring session ticket for new sessions. Renewal requires the same channel, user UID, and matching ticket.

## Next.js Rewrites

`web/next.config.ts` registers these only when `AGENT_BACKEND_URL` is set:

| Source             | Destination                                  |
| ------------------ | -------------------------------------------- |
| `/api/get_config`  | `${AGENT_BACKEND_URL}/get_config`             |
| `/api/startAgent`  | `${AGENT_BACKEND_URL}/startAgent`             |
| `/api/stopAgent`   | `${AGENT_BACKEND_URL}/stopAgent`              |

`verify-api-contracts.ts` asserts that no `web/app/api/**/route.ts` files exist. Adding one would create a competing handler in front of the rewrite — don't.

## Environment Variables

| Scope                  | Variable                                  |
| ---------------------- | ----------------------------------------- |
| Python server (required) | `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE` |
| Python server (optional) | `PORT`, `AGENT_ALLOWED_ORIGINS`, `MURF_API_KEY` |
| Next build             | `AGENT_BACKEND_URL`                       |

`AGENT_BACKEND_URL` is a Next **server**-time env var (used inside `next.config.ts`), not a `NEXT_PUBLIC_*` value — do not prefix it.

## Token Shape

`get_config` returns:

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "app_id": "string",
    "token": "string",          // generated server-side; token_expire=3600
    "uid": "string",            // serialized number
    "channel_name": "string",
    "agent_uid": "string",
    "session_ticket": "string"  // signed capability; expires after 3600 seconds
  }
}
```

The same Agora token grants RTC and RTM privileges. The session ticket is an
application capability, not an Agora token or user authentication credential.

## Managed Agent Payload

`server/src/agent.py` builds the managed agent with the installed Agora SDK
(`AgoraAgent(...).with_stt(...).with_llm(...).with_tts(...)`) rather than
posting a hand-written JSON payload. It enables RTM and metrics, disables tools,
and creates a numeric-UID async session. The exact builder arguments and
turn-detection settings are maintained in
[Managed Agent Config](L2/managed_agent_config.md).

## RTM Event Shapes (Client-Side)

`AgoraVoiceAI` emits the same toolkit events as the other quickstarts:

- `TRANSCRIPT_UPDATED` — `{ uid, text, status, timestamp }[]`
- `AGENT_STATE_CHANGED` — `AgentState`
- `AGENT_METRICS` — `{ type, name, value, timestamp }`
- `MESSAGE_ERROR` — `{ module, code, message, send_ts }`
- `MESSAGE_SAL_STATUS` — `{ status, timestamp }`
- `AGENT_ERROR` — SDK error info

`ConversationComponent.tsx` also attaches a raw RTM `message` listener as a fallback for the same `message.error` / `message.sal_status` payloads.

`ConversationComponent` also records RTC connection-state changes locally.
Transcript events with `TurnStatus.INTERRUPTED` are displayed as interrupted
turns. These runtime records are not persisted.

## Internal Types

| Type                          | Lives in                                       | Notes                                            |
| ----------------------------- | ---------------------------------------------- | ------------------------------------------------ |
| `StartAgentRequest`           | `server/src/server.py`                         | pydantic, camelCase fields                       |
| `StopAgentRequest`            | `server/src/server.py`                         | pydantic, agent ID and ticket-bound session identity |
| `AgoraTokenData`              | `web/src/types/conversation.ts`                | Used by `LandingPage` + `ConversationComponent`  |
| `AgoraRenewalTokens`          | `web/src/types/conversation.ts`                | Renewal handler payload                          |
| `ConversationComponentProps`  | `web/src/types/conversation.ts`                | Includes RTM client + data                       |
| `GetConfigResponse`           | `web/src/services/api.ts`                      | Browser shape for `data` field                   |

## Related Deep Dives

- [Managed Agent Config](L2/managed_agent_config.md) — Detailed field reference.
- [Verification Scripts](L2/verification_scripts.md) — How the contracts above are enforced by local pre-ship checks.
