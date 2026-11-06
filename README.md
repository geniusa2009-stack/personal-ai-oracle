# Personal AI Oracle — Hybrid Cloud + Mac Agent

Personal AI Oracle is a private hybrid personal-agent system:
- A private cloud dashboard and control plane remain available when the MacBook is offline.
- A persistent Mac agent initiates an outbound HTTPS connection to the cloud and executes the current read-only remote Mac tasks; consequential mutations are gated locally until a signed approval exchange is implemented.
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
- The Mac creates the outbound HTTPS connection. No public inbound service is opened on the Mac. The remote API allowlist currently exposes read-only Mac tools only; cloud-originated write/move/delete/command/app-launch jobs are rejected until a one-time approval capability can be verified independently by the Mac agent.
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


## Intelligence layer: knowledge graph and automatic model tiers

Oracle can enrich a request with a small, scope-isolated knowledge-graph context.
Only entities and relationships explicitly saved through `knowledge_graph.py`
are retrieved; graph records are bounded and treated as untrusted context.

Automatic quality-tier routing is **off by default**. Enable it in the private
local environment file with:

```env
ORACLE_AUTO_MODEL_ROUTING=true
ORACLE_MODEL_TIER_FAST=<provider-model-id>
ORACLE_MODEL_TIER_BALANCED=<provider-model-id>
ORACLE_MODEL_TIER_DEEP=<provider-model-id>
ORACLE_PROVIDER_TIER_FAST=<configured-provider>
ORACLE_PROVIDER_TIER_BALANCED=<configured-provider>
ORACLE_PROVIDER_TIER_DEEP=<configured-provider>
```

Task-specific `ORACLE_MODEL_<TASK>` / `ORACLE_PROVIDER_<TASK>` settings take
precedence over tier settings. Explicit role-level provider/model settings take
precedence over automatic selection. Oracle does not silently switch providers
when a selected provider is unavailable: configure the intended provider/model
and its credentials first. This avoids unexpected data transfers or costs.


## Workflow trace and execution history

When enabled (default), each agent run receives a workflow ID and writes a durable
execution trace to the configured SQLite database. The ledger stores task, input,
and output **SHA-256 digests**, tool IDs, statuses, elapsed time, and timestamps;
it does not store task text, local file contents, tool arguments, or tool outputs.
Trace rows are scope-isolated and can be cleared using the existing panic-wipe
allowlist. Set `ORACLE_ENABLE_WORKFLOW_LEDGER=false` to disable trace creation,
or `ORACLE_WORKFLOW_SCOPE` to choose a stable owner scope when no memory scope
is passed to the orchestrator. A step left in `running` state is visible as an
interrupted checkpoint; automatic replay/resume is not enabled by this ledger.


## Deep Research Engine

The Planner can now select `web.deep_research` for evidence-heavy questions. The
research engine asks the Researcher for up to four distinct search queries, searches
and deduplicates normalized HTTP(S) sources, and can extract up to six pages through
Oracle's isolated browser. In cloud mode, public search runs in the cloud while page
navigation is dispatched to the paired Mac agent.

Each source receives a stable per-report citation ID (`[S1]`, `[S2]`, ...).
The synthesis is checked against the actual source IDs; unknown model-generated
citations are flagged instead of being treated as valid. Reports distinguish
extracted page text from search-snippet-only evidence and expose limitations,
queries, URLs and source-domain hints. Domain hints are not reliability guarantees.

Research limits are bounded in code (up to 4 queries, 12 sources, 6 page fetches
and a 26,000-character synthesis context). Raw research page contents are returned
for the current run only and are not persisted by the research engine.


## Oracle Control Center

The Streamlit dashboard now includes an Oracle Control Center that shows workflow
execution metadata, specialist/provider assignments, configured quality tiers,
and the owner-scoped Knowledge Graph. It supports explicitly adding entities and
directed relationships, searching the saved graph context, and running Deep
Research directly from the dashboard. Workflow history remains digest-only;
Knowledge Graph records are explicitly user-entered (the system does not silently
infer or save relationships from private conversations).
