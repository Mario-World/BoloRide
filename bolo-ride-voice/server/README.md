# Agora Agent Service

Agora Conversational AI Agent service built with FastAPI.

## Quick Start

Use the repo-root [README.md](../README.md) for the normal full-stack local flow. This document is for working on the Python backend module directly.

Recommended from the repo root.

Repo setup:

```bash
bun run setup
```

Setup preserves a configured `server/.env` and copies a legacy `server/.env.local` when needed. The completion message reflects the credential state. Setup and `doctor:local` replace an untouched example file with configured legacy credentials.

Agora credentials:

```bash
agora quickstart env write .
```

Run the app:

```bash
bun run dev
```

This assumes the Agora CLI is installed and logged in. The command uses the project selected in your Agora CLI context, which is usually your default account project.

If you are not using the Agora CLI, create the env file manually and fill in your project values:

```bash
cp server/.env.example server/.env
```

From `server/`:

### 1. Configure Environment

Backend-only Agora CLI env write:

```bash
agora quickstart env write ..
```

Manual fallback:

```bash
cp .env.example .env
```

`.env.example` is the reference template. If you are not using the Agora CLI, edit `.env` and fill in your Agora credentials:
- `AGORA_APP_ID` - Your Agora App ID (Required)
- `AGORA_APP_CERTIFICATE` - Your Agora App Certificate (Required)
- `AGENT_ALLOWED_ORIGINS` - Comma-separated web origins allowed by FastAPI CORS
- `AGENT_PUBLIC_URL` - Public base URL for Agora server-side REST tool callbacks
- `BUSINESS_API_URL` - Business API base URL reachable by the voice service
- `BUSINESS_API_KEY` - Server-only key shared with the business API
- Agora managed provider access should be enabled for this project

If you still need to authenticate with the CLI:

```bash
agora login
```

To select a specific existing project before writing env values:

```bash
agora project use <project-id-or-name>
agora quickstart env write ..
```

To create a new project instead of using your default project:

```bash
agora project create my-first-voice-agent --feature rtc --feature convoai
agora project use my-first-voice-agent
agora quickstart env write ..
```

**Note**: The service generates RTC/RTM tokens from `AGORA_APP_ID` and
`AGORA_APP_CERTIFICATE`, and signs short-lived session tickets using a
domain-separated key derived from the certificate. Both secrets stay server
side. The managed chain is `DeepgramSTT` (`nova-3`, English) +
`OpenAI` (`gpt-4o-mini`) + `MiniMaxTTS`
(`speech_2_6_turbo` / `English_captivating_female1`).

To enable booking tools, configure all three server-only values:

- `BUSINESS_API_URL` - URL reachable from this FastAPI service, e.g.
  `http://127.0.0.1:8010` for the local business API.
- `BUSINESS_API_KEY` - the same server-only key configured on the business API.
- `AGENT_PUBLIC_URL` - absolute HTTP(S) URL through which Agora's service can
  reach this FastAPI instance. Local voice-agent tests require a public HTTPS
  tunnel; `localhost` is not reachable by Agora.

The Agora service exposes a narrow REST tool set backed by the business API:
validate details, estimate fare, create/retrieve/cancel a booking, and create,
retrieve, or verify a payment. Booking creation requires a current backend fare
and explicit passenger confirmation. Payment simulation is deliberately not an
LLM-callable tool; an order is not successful until the backend returns
`VERIFIED`. The business API and its database remain authoritative.

If any tool configuration value is missing, the agent starts in voice-only
mode and must not claim to book a ride or process a payment. See the parent
[voice-agent architecture](../ARCHITECTURE.md) for the complete tool flow and
known limitations.

### 2. Install Dependencies

**Option A: Using Virtual Environment (Recommended)**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Option B: Global Installation (Not Recommended)**
```bash
pip install -r requirements.txt
```

### 3. Start Service

```bash
# If using virtual environment, make sure it's activated first
python src/server.py
```

The service will start on port 8000 (or the port specified in `.env`).

## How This Fits The Repo

- Full-stack local development: run `bun run dev` from the repo root. The browser still calls Next `/api/*`, and Next rewrites those requests to this FastAPI service.
- Module-local backend work: use the commands in this README when you only need to run or inspect the Python service itself.
- Deployment: this Python service is required because the web app only forwards API requests through `AGENT_BACKEND_URL`.

### 4. Test API

```bash
# Request an initial session configuration (contains a short-lived session ticket)
curl http://localhost:8000/get_config

# Start and stop requests must include the returned session ticket and session identity.
# Use the browser flow or the FastAPI /docs page to copy values from each response.
#
# POST /startAgent: channelName, rtcUid, userUid, sessionTicket
# POST /stopAgent: agentId, channelName, userUid, sessionTicket
#
# Do not log, commit, or share session tickets.
```

## API Endpoints

- `GET /get_config` - Create a session (no query) or renew a token using a
  ticket-bound `channel`, `uid`, and `session_ticket`.
- `POST /startAgent` - Start the agent for the initialized session. Returns a
  ticket bound to the returned agent ID.
- `POST /stopAgent` - Stop only the agent ID bound to its session ticket.

The browser renews the same concrete RTC/RTM UID before the one-hour token
expires. FastAPI restricts CORS through `AGENT_ALLOWED_ORIGINS`; this does not
replace product authentication or rate limiting.

The repo-level `bun run verify:local:fastapi` check exercises this FastAPI app through the Next proxy path, but it swaps in a fake agent implementation so route wiring can be verified without depending on a live agent start. Python unit tests use fake Agora sessions and a fake business API; passing them does not verify a live Agora call or public tunnel.

## Requirements

- Python >= 3.10
- Dependencies listed in `requirements.txt`

## SDK

This project uses `agora-agents` (import `agora_agent`):
- Package: `agora_agent`
- Agent builder: `agora_agent.agentkit.Agent` with fluent `.with_llm()` / `.with_tts()` / `.with_stt()` API
- Default vendors: `DeepgramSTT`, `OpenAI`, `MiniMaxTTS` from `agora_agent.agentkit.vendors`
- Optional BYOK examples in `src/agent.py`: `DeepgramSTT`, `OpenAI(api_key=...)`, `ElevenLabsTTS`
- Token: `agora_agent.agentkit.token.generate_convo_ai_token`
