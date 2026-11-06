# Personal AI Oracle — Hybrid Cloud + Mac Agent

Personal AI Oracle is a private hybrid personal-agent system:
- A private cloud dashboard and control plane remain available when the MacBook is offline.
- A persistent Mac agent initiates an outbound HTTPS connection to the cloud and executes approved Mac-local tasks.
- Multi-provider models can be assigned independently to the assistant, planner, researcher, coder, writer, executor and reviewer.
- An isolated Playwright browser on the Mac can search, navigate, read webpages and list links.
- The local Mac remains the execution endpoint for local files, local apps, developer tools and browser sessions.

The cloud does not open an inbound port on the Mac. Device communication is Mac-initiated HTTPS polling with short-lived task leases and one-time result submission.

## Architecture

| Component | Runs where | Responsibility |
|---|---|---|
| Cloud dashboard | Private cloud web service | Authenticated workspace, Oracle features, chat, job status |
| Cloud control API | Private cloud web service | Device pairing, authenticated job queue, leases, results |
| Mac agent | Logged-in Mac user session | Outbound connection, local actions, browser execution |
| Playwright browser | Mac | Dedicated browser profile, public website navigation and extraction |
| Model router | Cloud and Mac | Provider/model selection by task and agent role |
| Local state | Mac | Device token, browser profile, local DB and audit records |
| Cloud state | Cloud persistent disk/DB | Device registry, job queue and job results |

## Cloud deployment

A two-service Render Blueprint is provided in `render.yaml`:
- `personal-ai-oracle-control`: FastAPI control plane with persistent storage.
- `personal-ai-oracle-web`: Streamlit private dashboard.

The services use Dockerfiles dedicated to their roles. The Blueprint creates a shared environment group for the control token so the API and dashboard receive exactly the same value. You can use another Docker-capable host by deploying `Dockerfile.cloud-api` and `Dockerfile.cloud-web` separately.

### Required secrets

Set these in the cloud provider's secret/environment settings. Use randomly generated values, at least 32 characters for the API tokens and at least 16 characters for the dashboard password.

| Variable | Control API | Cloud dashboard | Mac |
|---|---:|---:|---:|
| `ORACLE_CLOUD_CONTROL_TOKEN` | Yes | Same exact value | No |
| `ORACLE_CLOUD_ENROLLMENT_TOKEN` | Yes | No | Same exact value for first pairing |
| `ORACLE_CLOUD_DASHBOARD_PASSWORD` | No | Yes | No |
| `ORACLE_CLOUD_API_URL` | No | Internal API URL | Public HTTPS API URL |
| `OPENROUTER_API_KEY` | No | Optional | Optional |
| `OPENAI_API_KEY` | No | Optional | Optional |
| `GEMINI_API_KEY` | No | Optional | Optional |
| `TAVILY_API_KEY` | No | Optional | Optional |

Use a different dashboard password and API tokens. Never put secrets in source files, GitHub commits, screenshots, or chat logs.

Configure the cloud web service with:
- `ORACLE_RUNTIME_MODE=cloud`
- `ORACLE_CLOUD_API_URL` pointing at the private/internal URL of the control API when the host supports it.
- `ORACLE_CLOUD_CONTROL_TOKEN` matching the API service value.
- `ORACLE_CLOUD_DASHBOARD_PASSWORD` set to a strong private password.
- `ORACLE_DB_PATH` on persistent storage if Oracle's feature data must survive redeploys.

The dashboard login is independent from the control API token. The control token is only used server-side by the dashboard and is not rendered into the browser UI.

For genuine 24/7 cloud availability, use an always-on service plan and persistent storage. Free tiers may sleep, restart or discard local container storage; do not rely on them for continuous background operation or durable state. Render documents that container filesystems are ephemeral without a persistent disk and that persistent disks are available on paid services. <https://render.com/docs/disks>

## Pair the MacBook

1. Deploy the API and web services and copy their HTTPS URLs.
2. In the Mac's private file `~/.personal_ai_oracle/.env`, set:

```dotenv
ORACLE_CLOUD_API_URL=https://YOUR-CONTROL-API.example.com
ORACLE_CLOUD_ENROLLMENT_TOKEN=THE_SAME_ENROLLMENT_SECRET_FROM_CLOUD
ORACLE_DEVICE_NAME=Personal MacBook
ORACLE_BROWSER_HEADLESS=1
ORACLE_BROWSER_ALLOW_PRIVATE_NETWORK=0
```

3. Restart the LaunchAgent. The Mac agent pairs once, stores its device token in `~/.personal_ai_oracle/device-token.json` with mode 0600, and begins polling for jobs.
4. The dashboard at the cloud web URL shows whether the Mac agent is online and can request Mac-local tools. Public web search remains available from the cloud; browser navigation, page extraction and local actions are dispatched to the Mac. If the Mac is asleep, powered off or disconnected, those Mac-dependent tasks remain queued and the dashboard reports that the agent is unavailable.

To install Chromium for the isolated browser once:

```bash
cd /path/to/personal-ai-oracle
.venv/bin/python -m playwright install chromium
```

For a visible browser window on the logged-in Mac desktop, set `ORACLE_BROWSER_HEADLESS=0`. The Oracle browser uses a separate profile under `~/.personal_ai_oracle/browser-profile`; it does not read or reuse the user's everyday Chrome/Safari profile. Any site sign-in should be performed manually in that dedicated browser window.

Private LAN and localhost destinations are blocked by default by the browser URL guard. Set `ORACLE_BROWSER_ALLOW_PRIVATE_NETWORK=1` only when you deliberately need to access a local development site or trusted LAN service.

## Multi-model routing

Supported providers in this revision:
- OpenRouter
- OpenAI
- Google Gemini
- Local Ollama

Configure defaults and per-role overrides using `ORACLE_DEFAULT_PROVIDER`, `ORACLE_AGENT_<ROLE>_PROVIDER`, `ORACLE_AGENT_<ROLE>_MODEL` and task-level `ORACLE_PROVIDER_<TASK>` / `ORACLE_MODEL_<TASK>`.

Roles: `assistant`, `planner`, `executor`, `researcher`, `coder`, `writer`, `reviewer`.

Hosted model requests are sent to the selected provider. Ollama model requests remain on the device where Ollama runs. The Mac agent needs an available local provider/model for its second review of consequential local write, move, delete and command operations.

## Security boundaries

- Cloud dashboard login and control API credentials are separate.
- Device credentials are random, stored hashed in the control-plane database, and returned only once at pairing.
- Jobs have bounded payloads, an allow-listed tool identifier, a lease token and a result size limit.
- The Mac creates the outbound HTTPS connection. No public inbound service is opened on the Mac.
- Browser automation uses an isolated profile and blocks non-global destinations by default to reduce SSRF and local-network exposure.
- Local tools run as the currently logged-in macOS user and use normal OS permissions. The agent does not escalate to root or bypass macOS privacy and safety protections.
- The system does not extract credentials from the user's ordinary browser profile. Sign in manually in the dedicated Oracle browser.
- Use HTTPS in production. Keep API tokens, model keys and device tokens out of source control.
- Remote tool outputs are bounded before upload; cloud results are retained for a configurable period (24-hour default) and terminal job metadata for 7 days.

## Local operation

Local-only mode remains supported:

```bash
python3 install_local.py
```

Dashboard: `http://127.0.0.1:8765`

If `ORACLE_CLOUD_API_URL` is configured in the Mac's private environment file, the LaunchAgent also starts the outbound cloud bridge automatically.

## Validation

CI runs Python compilation and the pytest suite, including cloud job validation, token hashing, browser URL validation, provider routing, local tools, agent planning, webhook validation and vault migration.

A successful CI run validates the code and API contracts; it does not by itself prove deployment credentials, cloud-provider configuration, browser binaries, or the user's physical Mac hardware are configured.
