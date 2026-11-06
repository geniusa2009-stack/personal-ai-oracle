# Personal AI Oracle — Local Mac Edition

Personal AI Oracle is a private, local-first AI workspace that runs on the owner's MacBook. It is **not a public website and is not configured for cloud deployment**.

The MacBook runs two supervised processes:
- A local Streamlit dashboard bound only to `127.0.0.1`.
- A background worker that runs the opportunity radar on a schedule.

A per-user macOS LaunchAgent starts Oracle when the owner logs in and restarts the runtime if it exits. On AC power, Oracle can use `caffeinate -s` to prevent idle system sleep. A MacBook that is powered off, logged out, asleep, or closed in a way that triggers sleep cannot run a 24/7 process.

## Local architecture

| File | Responsibility |
|---|---|
| `app.py` | Local Streamlit dashboard and chat |
| `local_runtime.py` | Supervises the UI and background worker |
| `manage_launch_agent.py` | Installs or removes the macOS LaunchAgent |
| `local_config.py` | Loads the private environment file from the user's home directory |
| `local_tools.py` | Local file, app and command tools for the agent |
| `agent_orchestrator.py` | Adaptive tool planning, execution and review |
| `agent_profiles.py` | Independent provider/model profiles for specialist agents |
| `ai_core.py` | Shared AI request, memory, routing and provider execution |
| `llm_provider.py` | OpenRouter, OpenAI, Gemini and Ollama provider adapters |
| `model_router.py` | Chooses a provider/model pair for each task |
| `memory.py` | Explicit, scope-isolated long-term memory |
| `db.py`, `database.py` | Local SQLite storage |
| `worker.py`, `radar.py` | Background opportunity discovery |

## Install on macOS

From the repository directory:

```bash
python3 install_local.py
```

The installer creates a project virtual environment, installs Python dependencies, creates the private local state directory, and registers the LaunchAgent.

Dashboard:

```
http://127.0.0.1:8765
```

To check the service, inspect the LaunchAgent and logs under:

```
~/.personal_ai_oracle/logs/
```

To stop and remove automatic startup (the database and keys are kept):

```bash
.venv/bin/python manage_launch_agent.py uninstall
```

To run Oracle manually without installing the LaunchAgent:

```bash
.venv/bin/python local_runtime.py
```

## Private configuration

Secrets and local settings live outside Git at:

```
~/.personal_ai_oracle/.env
```

The file should be readable only by the current user:

```bash
chmod 600 ~/.personal_ai_oracle/.env
```

Example configuration:

```dotenv
# Default assistant provider/model
ORACLE_DEFAULT_PROVIDER=openrouter
OPENROUTER_API_KEY=
OPENROUTER_MODEL=deepseek/deepseek-chat

# Other hosted providers
OPENAI_API_KEY=
OPENAI_MODEL=
GEMINI_API_KEY=
GEMINI_MODEL=

# Local model server (Ollama)
ORACLE_OLLAMA_ENABLED=1
OLLAMA_BASE_URL=http://127.0.0.1:11434/v1
OLLAMA_MODEL=

# Specialist agent profiles can use different providers and models
ORACLE_AGENT_PLANNER_PROVIDER=ollama
ORACLE_AGENT_PLANNER_MODEL=
ORACLE_AGENT_EXECUTOR_PROVIDER=ollama
ORACLE_AGENT_EXECUTOR_MODEL=
ORACLE_AGENT_RESEARCHER_PROVIDER=gemini
ORACLE_AGENT_RESEARCHER_MODEL=
ORACLE_AGENT_CODER_PROVIDER=openai
ORACLE_AGENT_CODER_MODEL=
ORACLE_AGENT_WRITER_PROVIDER=openrouter
ORACLE_AGENT_WRITER_MODEL=
ORACLE_AGENT_REVIEWER_PROVIDER=openrouter
ORACLE_AGENT_REVIEWER_MODEL=

# Optional per-task provider/model routing
ORACLE_PROVIDER_FAST=
ORACLE_MODEL_FAST=
ORACLE_PROVIDER_REASONING=
ORACLE_MODEL_REASONING=
ORACLE_PROVIDER_CODING=
ORACLE_MODEL_CODING=
ORACLE_PROVIDER_RESEARCH=
ORACLE_MODEL_RESEARCH=
ORACLE_PROVIDER_WRITING=
ORACLE_MODEL_WRITING=
ORACLE_PROVIDER_CREATIVE=
ORACLE_MODEL_CREATIVE=

# Agent, storage and background task settings
ORACLE_MAX_AGENT_STEPS=12
ORACLE_MEMORY_SCOPE=user:oracle-owner
ORACLE_LOCAL_PORT=8765
ORACLE_PREVENT_IDLE_SLEEP=1
SCAN_INTERVAL_HOURS=12
TAVILY_API_KEY=
WA_ACCESS_TOKEN=
WA_PHONE_NUMBER_ID=
WA_AUTO_REPLY=draft
```

Do not commit this file or paste real keys into source code. Oracle loads it at startup; restart the LaunchAgent after editing it.

## Multi-model and multi-agent routing

Oracle supports four provider adapters:
- **OpenRouter** — hosted models through one provider key.
- **OpenAI** — direct OpenAI API access.
- **Google Gemini** — Gemini through Google's OpenAI-compatible endpoint.
- **Ollama** — models running on the Mac at `127.0.0.1:11434`; local requests do not need a cloud key.

The dashboard has a default provider/model selector. Specialist agents can independently select a provider and model using `ORACLE_AGENT_<ROLE>_PROVIDER` and `ORACLE_AGENT_<ROLE>_MODEL`.

Current roles: `assistant`, `planner`, `executor`, `researcher`, `coder`, `writer`, and `reviewer`.

This means the planner, researcher, coder and reviewer do not have to use the same model. Their chosen settings are visible in the dashboard's sidebar.

Ollama must be installed and a model must be present locally before selecting it. Hosted providers still send their prompts to their respective services; selecting local hosting does not make a cloud provider's requests local.

## Local agent capabilities

Agent Mode is enabled by default. The agent can use Oracle features plus local file and application tools, and can run supported developer commands under the currently logged-in macOS user account. It does not run as root and does not bypass macOS privacy permissions or system protections. Local tool activity is recorded in a content-free audit file at:

```
~/.personal_ai_oracle/logs/local-actions.jsonl
```

The agent has a configurable step budget (`ORACLE_MAX_AGENT_STEPS`, default 12) to prevent a planning loop from running forever. Set a value up to 30 for longer workflows.

## Storage and backups

The SQLite database is stored at:

```
~/.personal_ai_oracle/oracle.db
```

The encrypted password vault uses `ORACLE_VAULT_KEY`. Back up the database and that key together. Losing the key means encrypted vault values cannot be recovered. Legacy Fernet/Base64 records are migrated transactionally when the vault is revealed after the new key is configured.

## WhatsApp note

The current project has WhatsApp Cloud API outbound/draft functionality and a signed Flask webhook implementation. A localhost-only service cannot receive Meta webhook events directly from the public internet. Incoming WhatsApp events need a separate local bridge or a deliberately configured inbound connection; Oracle does not expose a public webhook service in this local edition.

## Validation

The repository CI runs:
- Python bytecode compilation.
- The full pytest suite, including provider routing, memory, local tools, agent planning, webhook validation and vault migration.
