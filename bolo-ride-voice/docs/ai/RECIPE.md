---
recipe_version: 1.0.0
recipe_status: experimental
extension_points:
  - id: api.routes
    name: Browser-facing API routes
  - id: agent.managed-config
    name: Managed agent prompt, VAD, model, and voice defaults
  - id: web.conversation-ui
    name: Conversation UI panels and controls
  - id: verification.contracts
    name: Contract and local smoke verification
invariants:
  - id: api.rewrite-boundary
    summary: Browser calls stay on /api/* and Next rewrites to FastAPI.
  - id: secrets.server-only
    summary: Agora App Certificate and BYOK keys stay in the Python backend.
  - id: token.uid-concrete
    summary: Backend generates concrete non-zero UIDs for new RTC+RTM sessions.
  - id: token.session-bound
    summary: Backend generates session identity and requires an HMAC-signed ticket for renewal and agent lifecycle calls.
stable_contracts:
  - id: env.required
    summary: AGORA_APP_ID and AGORA_APP_CERTIFICATE are required by FastAPI; AGENT_BACKEND_URL is required by deployed web rewrites.
  - id: api.core-routes
    summary: GET /api/get_config, POST /api/startAgent, and POST /api/stopAgent remain the browser-facing contract.
  - id: response.envelope
    summary: Successful backend responses use { code, msg, data }.
---

# Recipe Contract

This base recipe defines the reusable surface for a Python-backed Agora Conversational AI quickstart with a Next.js web client.

## Recipe Role

- Role: `base` quickstart recipe.
- Target audience: developers bootstrapping a production-style Conversational AI app with a Python FastAPI backend and Next.js web client.
- Reuse model: clone, bind project, run, then customize backend agent behavior or browser UI.

## Recipe Scope

This base recipe provides a copyable split-process starter with:

- Python FastAPI token generation and managed agent lifecycle.
- Next.js browser UI with RTC audio, RTM events, transcript, metrics, and connection status.
- Rewrite-only `/api/*` browser facade that hides backend placement.
- Managed default STT, LLM, and TTS provider configuration.
- Contract and local smoke verification that do not require live Agora calls.

## Baseline Implementation Guidance

This repository is the Python-backed Agora quickstart baseline for this recipe. Agents should use this repo's source and progressive disclosure docs as the starting point, then customize.

Do not recreate Agora ConvoAI integration from memory. Provider schemas, SDK builder fields, token behavior, and RTM event details can drift. For a new baseline implementation, follow [L1/L2/from_scratch_bootstrap.md](L1/L2/from_scratch_bootstrap.md) while copying verified patterns from this repo.

## Extension Points

| ID | Surface | How to extend | Required follow-up |
| -- | ------- | ------------- | ------------------ |
| `api.routes` | `server/src/server.py`, `web/next.config.ts`, `web/src/services/api.ts` | Add FastAPI route, add rewrite, add browser fetch helper. | Extend `web/scripts/verify-api-contracts.ts`; add smoke coverage if the route belongs in local verification. |
| `agent.managed-config` | `server/src/agent.py` | Change `_system_prompt`, `VOICE_LANGUAGES`, `turn_detection`, `OpenAI`, `DeepgramSTT`, `_tts_for_language`, `parameters`, or session options. | Run backend compile and local FastAPI smoke checks; document new env vars in `server/.env.example`. |
| `web.conversation-ui` | `web/src/components/*`, `web/src/lib/conversation.ts` | Customize pre-call, transcript, metrics, connection status, microphone, or visualizer UI. | Preserve RTC/RTM lifecycle ownership and transcript UID normalization. |
| `verification.contracts` | `web/scripts/*.ts`, root `package.json` | Add contract checks for new browser/backend boundaries. | Keep checks runnable without live Agora credentials where possible. |

## Invariants

- Browser code calls only `/api/get_config`, `/api/startAgent`, and `/api/stopAgent` for the default recipe flow.
- Next.js owns the browser-facing `/api/*` paths only through rewrites; do not add `web/app/api/**/route.ts` for agent or token logic.
- FastAPI owns token generation, `AGORA_APP_CERTIFICATE`, BYOK provider keys, and agent lifecycle.
- The backend returns one RTC+RTM-capable token from `get_config` for a server-generated concrete UID.
- The backend returns an HMAC-signed, expiring session ticket; renewal and agent start/stop requests must present the ticket and matching session identity.
- `LandingPage.tsx` coordinates config fetch, agent start, RTM login, token renewal, and call teardown.
- `ConversationComponent.tsx` owns RTC join, microphone publish, `AgoraVoiceAI` initialization, transcript/state/metrics listeners, and explicit end-call media release.
- Managed-provider defaults stay server-side unless a change intentionally adds a BYOK path.

## Stable Contracts

| Contract | Stable shape |
| -------- | ------------ |
| Required backend env | `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE` |
| Optional backend env | `PORT`, `AGENT_ALLOWED_ORIGINS` |
| Required web deploy env | `AGENT_BACKEND_URL` |
| `GET /api/get_config` | No query creates a session; renewal requires `channel`, `uid`, and `session_ticket`. Returns `data.app_id`, `data.token`, `data.uid`, `data.channel_name`, `data.agent_uid`, `data.session_ticket`. |
| `POST /api/startAgent` | Body `{ channelName, rtcUid, userUid, sessionTicket, parameters? }`; returns `data.agent_id`, `data.channel_name`, `data.status`, `data.session_ticket`. |
| `POST /api/stopAgent` | Body `{ agentId, channelName, userUid, sessionTicket }`; returns `{ code: 0, msg: "success" }`. |
| Success envelope | `{ "code": 0, "msg": "success", "data": ... }` where route has data. |
| Verification entry points | `bun run verify:web`, `bun run verify:backend`, `bun run verify:web:proxy`, `bun run verify:local:fastapi`, `bun run verify:local`. |

## Internal / Subject to Change

- Exact visual layout, component composition, Tailwind classes, and asset choices under `web/src/components/`.
- Exact managed-provider model names, VAD timing, voice IDs, and prompt text, as long as they remain documented extension points.
- In-memory `Agent._sessions` implementation details; the stable behavior is ticket-bound start and stop by returned `agent_id`.
- Verification implementation internals under `web/scripts/`; the stable surface is the root script names and what they assert.
- `agora-agents` SDK minor-version behavior; this recipe lower-bounds v2 but does not freeze every SDK field.

## Related Progressive Disclosure Docs

- `L1/01_setup.md` — setup, env, and command reference.
- `L1/02_architecture.md` — request flow and component topology.
- `L1/05_workflows.md` — common modification workflows.
- `L1/06_interfaces.md` — route, rewrite, env, and event contracts.
- `L1/L2/from_scratch_bootstrap.md` — implementation map for recreating the Python-backed quickstart recipe.
- `L1/L2/managed_agent_config.md` — full agent config detail.
- `L1/L2/session_lifecycle.md` — RTC/RTM/session orchestration.
