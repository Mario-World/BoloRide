# Bolo Ride

Bolo Ride is a voice-first ride-booking application targeting Telugu, Hindi,
Kannada, and English. The workspace preserves two separate Agora voice
quickstarts and now includes an isolated simulated booking/payment API plus a
watchable web demo. The booking flow is not yet connected to the live Agora
conversation or Android client.

## Current Workspace

| Path | Current contents |
| --- | --- |
| `app/` | Tracked Kotlin + Jetpack Compose Agora voice-conversation demo. |
| `server/app/` | Tracked FastAPI service for Agora tokens, conversation lifecycle, and an in-memory session store. |
| `bolo-ride-voice/web/` | Next.js voice client for the Agora Python quickstart foundation. |
| `bolo-ride-voice/server/` | FastAPI Agora-agent service with Bolo Ride's English-only conversation prompt. Separate from root `server/app/`. |
| `services/business-api/` | Separate FastAPI business API, SQLAlchemy persistence, Alembic migration, deterministic ride simulator, and mock payments. |
| `docker-compose.demo.yml` | Local PostgreSQL + business API + Next.js demo stack. |
| `docs/` | Setup and architecture guidance for the tracked Android quickstart. |

The Agora Python foundation remains a separate implementation from the root
Android quickstart; no files have been moved or merged. Its local
`server/.env` is ignored by the subtree's `.gitignore`. Keep credentials out of
the frontend and Android client.

## Quick Demo (Windows, no Docker required)

Install the business API Python dependencies and web dependencies once, then
from the repository root run:

```powershell
python -m pip install -r services\business-api\requirements.txt
Set-Location bolo-ride-voice\web
bun install
Set-Location ..\..
.\scripts\demo.ps1
```

Open [http://localhost:3000/demo](http://localhost:3000/demo). The script runs
the business API and web app locally with SQLite and simulated rides/payments;
press **Ctrl+C** in that terminal to stop both services. The demo database is
kept under the ignored `services\business-api\.demo\` folder.

### Optional PostgreSQL demo with Docker

If Docker Desktop is running, the same demo can use PostgreSQL:

```powershell
docker compose --env-file .env.example -f docker-compose.demo.yml up --build
```

Open [http://localhost:3000/demo](http://localhost:3000/demo). The interactive
flow calls the real business API through a server-side Next.js proxy: estimate
a fare, explicitly confirm a booking, advance the simulated ride, and submit
and verify a mock payment. No real ride or payment is created. The voice
quickstart is still separate; configure its own Agora server credentials to
test a live voice conversation.

See [the business API guide](services/business-api/README.md) and
[API contract](services/business-api/API.md) for environment variables,
migrations, routes, and test scope.

## Current Gaps

- Booking and payment APIs are not yet connected as tools to the Agora agent or
  integrated into the Android client.
- The Agora Python foundation is configured for English; Telugu, Hindi,
  Kannada, and code-mixed speech have not been verified.
- The Compose app remains the Agora quickstart interface, not the complete
  passenger booking/payment UI.
- No product-user authentication or production payment/ride provider is
  implemented; the demo uses a local-only mock key and simulated providers.

## Architecture and Plan

- [Architecture and current-state assessment](ARCHITECTURE.md)
- [Development roadmap and proposed file changes](ROADMAP.md)
- [Existing Android setup](docs/setup.md)
- [Existing Android architecture](docs/architecture.md)
- [Agora Python + Next.js prototype documentation](bolo-ride-voice/README.md)

The Agora Python quickstart and the business API remain separate services.
Large-scale repository consolidation is still intentionally deferred.

## Existing Android Quickstart

The root `app/` and `server/` are the original Agora Android quickstart. The
following setup and build instructions apply to that implementation only; they
do not configure the separate `bolo-ride-voice/` web prototype.

### Release 1.1.0 — Agora Conversational AI v2.12

This release integrates the Conversational AI Engine's v2.12 features with
`agora-agents==2.8.1` on the Python backend. Android uses RTC `4.6.4` and RTM
`2.3.0`. Engine, Python SDK, and Android SDK versions are independent.

See [the changelog](CHANGELOG.md) and [setup instructions](docs/setup.md) for
the Android client, Python server, and local tunnel workflow.

### Prerequisites

- Android Studio with JDK 17 or newer
- Python 3.10 or newer
- Bash for the scripts in `server/`
- An Android device or emulator with microphone support
- An Agora account with access to Conversational AI
- A development tunnel provider; the included helper supports Cloudflare Tunnel, ngrok, Tailscale Funnel, and LocalTunnel

The commands below assume a macOS or Linux shell. On Windows, run the backend scripts from WSL or an equivalent Bash environment.

### Quick Start

#### 1. Install the Agora CLI and sign in

Skip this step if `agora` is already on your `PATH`.

```bash
curl -fsSL https://dl.agora.io/cli/install.sh | sh
agora --help
agora login
```

#### 2. Get the quickstart

The recommended path lets the CLI clone the template and bind an Agora project. Replace `my-android-demo` with your app folder name:

```bash
agora init my-android-demo --template android
cd my-android-demo
```

`agora init` selects or creates an Agora project and records the project binding in `.agora/project.json`.

To work from an existing clone instead:

```bash
git clone https://github.com/AgoraIO-Conversational-AI/agent-quickstart-android.git
cd agent-quickstart-android
```

If you use an existing clone, you will select the Agora project when you configure the server in the next step.

#### 3. Configure and run the Python server

```bash
python3 -m venv server/.venv
source server/.venv/bin/activate
pip install -r server/requirements-dev.txt
cp -n server/.env.example server/.env.local
agora project env write server/.env.local --template standard
./server/run.sh
```

The command above uses the project selected by `agora init`. For an existing clone, select the project explicitly instead:

```bash
agora project env write server/.env.local \
  --project <project-name-or-id> \
  --template standard
./server/run.sh
```

The server listens on `http://127.0.0.1:8000` and keeps `AGORA_APP_CERTIFICATE` off the Android device. Leave this terminal running. The local endpoint uses HTTP; the selected tunnel provider supplies the public HTTPS endpoint required by Android.

#### 4. Create a temporary public HTTPS URL

In another terminal, run:

```bash
./server/tunnel.sh --provider ngrok
```

Choose `cloudflare`, `ngrok`, `tailscale`, or `localtunnel` with `--provider`. Keep the tunnel running and copy its generated `https://` URL.

Verify that the public endpoint reaches the Python server:

```bash
curl https://your-public-host/health
```

The response must be backend health JSON, not a tunnel-provider login or warning page. See [Local HTTPS tunnels](docs/local-tunnels.md) for explicit ngrok, Cloudflare Tunnel, Tailscale Funnel, and LocalTunnel commands.

#### 5. Configure Android

Write the public server URL to root `local.properties`:

```bash
./server/configure-android.sh https://your-public-host
```

The script writes only this client value:

```properties
QUICKSTART_SERVER_URL=https://your-public-host
```

Do not put `AGORA_APP_CERTIFICATE` in `local.properties`.

#### 6. Build the app

```bash
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" ./gradlew :app:assembleDebug
```

If your shell already uses JDK 17 or newer, `./gradlew :app:assembleDebug` is sufficient.

#### 7. Run it

Open the project in Android Studio, or run it from the command line, then launch it on a device or emulator.

Tap **Start voice session**, allow microphone permission, speak to the agent, and watch transcripts appear in real time.

If the agent does not join or transcripts do not appear, run:

```bash
agora project doctor --deep
```

If the temporary tunnel URL changes, run `server/configure-android.sh` again, rebuild, and reinstall the app. For manual setup, optional configuration, and production notes, see [docs/setup.md](docs/setup.md).

## What To Read First

If you are using this as a template, start here:

- [ConversationScreen.kt](app/src/main/java/com/androidengineers/agent_quickstart_android/ui/ConversationScreen.kt)
- [ConversationViewModel.kt](app/src/main/java/com/androidengineers/agent_quickstart_android/ui/ConversationViewModel.kt)
- [AgoraConversationSessionManager.kt](app/src/main/java/com/androidengineers/agent_quickstart_android/rtc/AgoraConversationSessionManager.kt)
- [ConversationAgoraApi.kt](app/src/main/java/com/androidengineers/agent_quickstart_android/data/ConversationAgoraApi.kt)
- [Python backend](server/app/main.py)

Those files show the full flow from UI action to Agora session setup.

## What To Customize First

Most teams will customize these pieces first:

1. `ConversationScreen.kt` for UI layout, branding, and session cards
2. `ConversationViewModel.kt` for app state, button actions, and session orchestration
3. `AgoraConversationSessionManager.kt` for RTC, RTM, and media behavior
4. `server/app/agora_client.py` for agent presets, geofence, and model configuration

## Build And Test

Run the Python server tests:

```bash
server/.venv/bin/python -m pytest server/tests
```

Compile Kotlin:

```bash
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" ./gradlew :app:compileDebugKotlin
```

Run unit tests:

```bash
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" ./gradlew :app:testDebugUnitTest
```

Assemble debug APK:

```bash
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" ./gradlew :app:assembleDebug
```

## Docs

- [Setup](docs/setup.md): CLI, server, tunnel, and Android configuration
- [Local HTTPS tunnels](docs/local-tunnels.md): expose the development server to a physical device
- [Backend runbook](docs/backend-runbook.md): local server, public tunnel, API contract, deployment, and smoke checks
- [Architecture](docs/architecture.md): app structure, code map, session lifecycle, and state flow
- [Troubleshooting](docs/troubleshooting.md): common setup, agent, RTM, metrics, and microphone issues
- [Agent coding guidance](docs/agent-guidance.md): Agora CLI skills and guidance for AI coding agents

## Security Note

`AGORA_APP_CERTIFICATE` stays in `server/.env.local` and is never compiled into Android. The Python server generates the Android user's RTC/RTM token and uses the Agora Python SDK to start, interrupt, and stop the agent. A development tunnel URL is public while the tunnel is running, so stop the tunnel when testing is complete and add appropriate application authentication before adapting this demo for production.
