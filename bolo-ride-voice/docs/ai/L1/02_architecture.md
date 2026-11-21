# 02 Architecture

> Split frontend + backend in one repo: Next.js browser app proxies `/api/*` to a Python FastAPI service that drives the Agora Conversational AI managed agent.

## High-Level Topology

```
   Browser tab                       Next.js (web/)               Python (server/)
   ┌────────────────────┐    fetch  ┌──────────────────────┐ HTTP ┌───────────────────────┐
   │ LandingPage.tsx    │──────────▶│ /api/get_config      │─────▶│ GET  /get_config      │
   │ ConversationCmp.tsx│           │ /api/startAgent      │─────▶│ POST /startAgent      │
   │ AgoraVoiceAI       │◀──────────│ /api/stopAgent       │─────▶│ POST /stopAgent       │
   │ agora-rtc-react    │  JSON     │ next.config.ts       │      │ FastAPI + CORS        │
   │ agora-rtm          │           │  rewrites()          │      │ AsyncAgora + AgoraAgent│
   └─────┬──────┬───────┘           └──────────────────────┘      └──────────┬────────────┘
         │      │ RTM data                                                   │ HTTPS
         │ RTC  │                                                            ▼
         ▼      ▼                                                Agora Conversational AI
   Agora media + RTM cloud                                       (managed STT/LLM/TTS)
```

## Voice Session Lifecycle

1. `LandingPage` calls `getConfig()` → `GET /api/get_config` → FastAPI creates random channel/UIDs and returns `data: { app_id, token, uid, channel_name, agent_uid, session_ticket }`.
2. In parallel:
   - `startAgent(channel_name, Number(agent_uid), Number(uid), session_ticket, language)` → `POST /api/startAgent` → FastAPI verifies the ticket and starts the managed agent in the selected response language; response contains an agent-bound ticket.
   - `new AgoraRTM.RTM(appId, uid).login({ token })` → wait for `CONNECTED` (10-second timeout) → `subscribe(channel_name)`.
3. `ConversationComponent` mounts inside a dynamic `AgoraRTCProvider` (RTC client in `useRef` for StrictMode safety) and:
   - `useJoin` joins RTC.
   - `useLocalMicrophoneTrack` + `usePublish` start mic publishing.
   - `AgoraVoiceAI.init({ rtcEngine, rtmEngine: rtmClient })` wires transcripts, state, metrics, and errors; `subscribeMessage(channel_name)` receives toolkit events.
   - `TurnStatus.INTERRUPTED` transcript turns are visibly labeled; agent state drives the visualizer.
4. End: `stopAgent(agentId, channel, uid, sessionTicket)` → `POST /api/stopAgent` → FastAPI verifies ticket ownership and stops the agent. The component releases the microphone, then `rtmClient.logout()` follows.
5. Renewal: on RTC `token-privilege-will-expire`, the client makes one ticket-authenticated `getConfig({ channel, uid, sessionTicket })` request and renews RTC and RTM with the same concrete UID.

The voice chain is Deepgram Nova-3 multilingual mode (`language="multi"`,
hints `en`, `hi`, `kn`, and `te`) → OpenAI `gpt-4o-mini` → Murf Falcon 2.1
(`Pooja`) when `MURF_API_KEY` is configured. The selected language maps to
`en-IN`, `hi-IN`, `kn-IN`, or `te-IN`. Without Murf, English and Hindi use the
managed MiniMax voice; Kannada and Telugu starts return a clear configuration
error. The selected response language is fixed per session, while multilingual
ASR can recognize code-switching. Agent VAD remains configured for interruptions
(`interrupt_duration_ms=160`, `prefix_padding_ms=300`) and turn-end silence
(`silence_duration_ms=480`).

## How `/api/*` Reaches FastAPI

`web/next.config.ts`:

```ts
async rewrites() {
  const backendUrl = process.env.AGENT_BACKEND_URL?.replace(/\/$/, '');
  if (!backendUrl) return [];
  return [
    { source: '/api/get_config',  destination: `${backendUrl}/get_config` },
    { source: '/api/startAgent',  destination: `${backendUrl}/startAgent` },
    { source: '/api/stopAgent',   destination: `${backendUrl}/stopAgent` },
  ];
}
```

If `AGENT_BACKEND_URL` is unset/empty, **no rewrites register** — the client cannot reach the backend. `bun run dev` always exports `AGENT_BACKEND_URL=http://localhost:8000` before starting Next.

## FastAPI Shape

`server/src/server.py`:

- `FastAPI(title="...", version="2.0.0")`.
- `CORSMiddleware` reads comma-separated origins from `AGENT_ALLOWED_ORIGINS`; credentials are disabled.
- Reads `server/.env` via `python-dotenv` at startup, resolved relative to `server/src/server.py`; host environment values take precedence.
- Constructs a single `Agent` instance at import time (`agent = Agent()`).
- Routes registered on an `APIRouter`: `GET /get_config`, `POST /startAgent`, `POST /stopAgent`.
- Session tickets are HMAC-signed with a domain-separated key derived from the server-only App Certificate. Renewal, start, and stop bind to the ticket claims.
- All successful responses use the envelope `{ "code": 0, "msg": "success", "data": ... }`.
- Errors funnel through `_to_http_error` → `HTTPException`; invalid input returns `400`, missing language-provider configuration returns `503`, and unexpected provider errors remain sanitized.
- `uvicorn.run(app, host="0.0.0.0", port=PORT)` under `if __name__ == "__main__":`.

`server/src/agent.py`:

- `get_config` treats missing, zero, and negative UIDs as "generate a usable UID" before minting an RTC+RTM token.
- `Agent.start(channel_name, rtc_uid, user_uid)` uses the module-level `AsyncAgora` client, builds `AgoraAgent` from `agora-agents` (`agora_agent`), and creates an async session.
- `Agent.stop(agent_id)` ends the session.

## Managed Agent Defaults (server/src/agent.py)

| Stage | Vendor       | Config highlights                                                          |
| ----- | ------------ | -------------------------------------------------------------------------- |
| STT   | `DeepgramSTT`| `model="nova-3"`, `language="multi"`, language hints `en`, `hi`, `kn`, `te` |
| LLM   | `OpenAI`     | `model="gpt-4o-mini"`, greeting/failure overrides, history settings        |
| TTS   | `MurfTTS` / `MiniMaxTTS` | Murf Falcon 2.1 / Pooja with selected locale; MiniMax fallback for English and Hindi |
| VAD   | Agora        | Tunable `turn_detection` dict with start/end mode and timing thresholds    |

Agent parameters: `data_channel="rtm"`, `enable_error_message=True`, `enable_metrics=True`. Advanced features: `{"enable_rtm": True, "enable_tools": False}`. Session options: `enable_string_uid=False`, `idle_timeout=30`, `expires_in=3600`.

The browser displays transcript, agent state, module errors, signaling errors,
and per-module latency metrics. These remain in memory; no webhook or durable
transcript store is configured.

## Why This Shape

- Python backend gives Python developers a familiar host for Conversational AI integration.
- Next.js rewrites hide backend placement from the browser — `/api/*` is the only URL the client knows.
- Single repo keeps web and backend changes reviewable together while preserving deploy separation.

## Related Deep Dives

- [Managed Agent Config](L2/managed_agent_config.md) — Full `agent.py` chain and tunable fields.
- [Session Lifecycle](L2/session_lifecycle.md) — Detailed client orchestration including renewal.
- [Verification Scripts](L2/verification_scripts.md) — How the contract harness asserts the proxy boundary.
