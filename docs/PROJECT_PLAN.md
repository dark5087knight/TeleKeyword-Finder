# Agent-Based Telegram Post Discovery & Orchestration System - Project Plan

Status: architecture phase. No implementation has started.
Scope of this document: requirements, architecture, data models, file structure, technology decisions, roadmap, risks.
Explicit decision: the project is built without LangChain. LLM access goes through small, hand-written provider adapters behind one interface.

## Table of Contents

1. [Decision Log](#1-decision-log)
2. [Project Overview](#2-project-overview)
3. [Requirements Analysis](#3-requirements-analysis)
4. [Architecture](#4-architecture)
5. [Components and Boundaries](#5-components-and-boundaries)
6. [Multi-User and Bring-Your-Own-LLM Design](#6-multi-user-and-bring-your-own-llm-design)
7. [Telegram Integration](#7-telegram-integration)
8. [LLM Usage Policy and Orchestrator Design](#8-llm-usage-policy-and-orchestrator-design)
9. [Post Discovery and Relevance Pipeline](#9-post-discovery-and-relevance-pipeline)
10. [Data Models](#10-data-models)
11. [Storage and Persistence](#11-storage-and-persistence)
12. [Scheduling and Execution Lifecycle](#12-scheduling-and-execution-lifecycle)
13. [Security and Reliability](#13-security-and-reliability)
14. [Project File Structure](#14-project-file-structure)
15. [Technology Decisions](#15-technology-decisions)
16. [Configuration Reference](#16-configuration-reference)
17. [Testing Strategy](#17-testing-strategy)
18. [Development Roadmap](#18-development-roadmap)
19. [Future Evolution](#19-future-evolution)
20. [Risk Register](#20-risk-register)
21. [Open Questions](#21-open-questions)

---

## 1. Decision Log

| ID | Decision | Status |
|---|---|---|
| D1 | Modular monolith, single process, single asyncio event loop | Decided |
| D2 | Control plane (bot, orchestrator, task manager) separated from execution plane (scheduler, workers) | Decided |
| D3 | A "task" is a data record run by a reusable worker on a central scheduler; no per-task LLM agent or process | Decided |
| D4 | The LLM only emits schema-validated typed commands from a closed set; deterministic code executes them | Decided |
| D5 | Relevance is a funnel: hard filters -> keyword prefilter -> LLM classifier. Most runs make zero LLM calls | Decided |
| D6 | No LangChain. Provider adapters: OpenAI-compatible (OpenAI, Groq, Gemini), Anthropic, optional Ollama | Decided |
| D7 | Multi-user with bring-your-own LLM key (OpenAI, Groq, Claude, Gemini; Ollama optional) | Decided |
| D8 | Interactive console chat for Upper Agent control; Telethon for reading channels and delivering matches | Decided |
| D9 | In-memory storage for milestones M1-M5 behind a TaskRepository interface | Decided |
| D10 | SQLite persistence (plus encrypted secret storage) at milestone M6, before any user LLM keys are stored | Recommended - needs confirmation |
| D11 | One operator-owned Telegram reading account for all users (public channels or channels that account already joined); users do not link their own Telegram accounts | Assumed - needs confirmation |
| D12 | Confirmation step before committing create / recipient change / channel change / cancel | Recommended |
| D13 | Delivery to designated recipients on Telegram | Recommended |
| D14 | PostgreSQL, LangGraph, Redis, Celery, FastAPI are not part of the MVP | Decided |

---

## 2. Project Overview

A conversational AI system controlled through an interactive terminal console. When launched, the user chats directly with the Upper Agent in natural language. For example:

"Monitor @channel1, @channel2 and @channel3. Find posts about AI agents, LLMs and new open-source models. Send relevant ones to recipient A. Check every five minutes."

The system turns that into a validated monitoring task, schedules it, and keeps running independently of the chat. Each run discovers new posts, evaluates relevance, delivers matches once, and records the outcome.

### Goals

- Support many independent tasks per user, each with its own channels, topics, recipient, schedule, status, checkpoint and history.
- Support multiple users, each using their own LLM provider and key.
- Answer status questions from real state, never from the LLM's guesses.
- Keep the LLM a restricted decision component, not a system controller.
- Start with the smallest reliable architecture and leave clean seams for growth.

### Non-goals (for the MVP)

- Reading channels with each user's own Telegram account.
- Auto-joining channels.
- Distributed infrastructure, microservices, a web dashboard.
- LangChain, LangGraph, PostgreSQL, Redis, Celery, FastAPI.
- Media analysis (images/video) -- media is link-only.

---

## 3. Requirements Analysis

### 3.1 Functional Requirements

- Task management via natural language: create, list, inspect, pause, resume, update (topics, channels, schedule, recipient), cancel.
- Clarification: ask follow-up questions when instructions are ambiguous or incomplete.
- Execution: recurring monitoring independent of the conversation.
- Pipeline: discover -> filter -> evaluate -> deliver -> record, with checkpoints and no duplicate deliveries.
- Diagnostics: "Why has task X delivered nothing in the last hour?" answered from execution records.
- User onboarding: each user registers an LLM profile (provider, models, key) and pairs recipients.
- Notifications: errors and state changes (task suspended, channel inaccessible, key invalid) go to the owning user.

### 3.2 Non-functional Requirements

- Isolation: one task's failure/pause/edit never affects another; one user's key failure never affects other users.
- Safety: closed command set; untrusted post content; secrets never reach an LLM.
- Resource control: bounded concurrency for executions, LLM calls and Telegram requests, per user and globally.
- Replaceability: LLM provider, storage and orchestration logic swappable behind interfaces.
- Testability: fakes for every external system (Telegram, LLMs, clock).
- Observability: structured logs without secrets; queryable execution history.
- Latency: minutes are acceptable; polling is fine.

### 3.3 Constraints

Python, asyncio, Telegram Bot API, Telethon, pytest. In-memory storage first. No PostgreSQL, LangGraph, Redis, Celery, FastAPI, or LangChain in the MVP.

### 3.4 Assumptions

| Assumption | Consequence if wrong |
|---|---|
| Recipients are chats the bot can message (users who pressed Start, or groups/channels containing the bot), registered per owner under an alias | Delivering to arbitrary users would require sending from a user account -- higher ban risk |
| New tasks start from "now" (checkpoint = latest message id), with optional lookback | If backfill is expected, creation can trigger a large LLM batch |
| The reading account must already have access; the system never auto-joins | Auto-join adds flood limits and ban risk |
| Delivered output is a bot-composed message: excerpt or summary, reason, permalink. Media is link-only | Forwarding originals from a bot is generally not possible |
| Access is controlled: an admin approves users | Open registration needs abuse controls (quotas, rate limits) |
| Polling every >= 60 seconds is acceptable | Real-time needs event handlers -- a different design |
| Each user pays for their own LLM usage through their own key | Operator-paid LLM usage needs budgets and billing |

### 3.5 Contradictions and Risks Identified

- "Runs independently" vs. in-memory storage. A restart wipes tasks, checkpoints, and (with multi-user) every user's LLM key. -> persistence at M6 (D10).
- "Create and activate immediately" vs. LLM fallibility. A misparsed recipient or channel list is a silent failure. -> confirm-before-commit (D12).
- Semantic relevance vs. "avoid unnecessary LLM calls." -> funnel (D5).
- Bots cannot read arbitrary channels. User-account reading carries ToS and ban risk. -> read-only, low frequency, no auto-join, one operator account (D11).
- Local and hosted LLMs return malformed structured output at different rates. -> schema constraints where available, always Pydantic validation plus one repair retry.
- Prompt injection via posts. -> post text never enters the orchestrator LLM; classifier has no tools.
- Telethon sessions must have a single owner. -> any future scale-out keeps Telegram I/O in one process.
- "Agent" terminology. "Create an agent" is UX wording; architecturally the user creates a task of type channel_monitor.
- Users' API keys are high-value secrets. -> encrypted storage, never logged, never sent to any LLM, captured through deterministic handlers.

---

## 4. Architecture

### 4.1 Principles

- Modular monolith over microservices.
- Separate control plane from execution plane.
- Business logic independent of Telegram handlers and the LLM provider.
- The LLM is a decision component with a closed command set.
- Deterministic code for scheduling, validation, authorization and lifecycle.
- Task state is isolated between tasks; single-writer rule per piece of state.
- Design for failure recovery and predictable behavior.
- No unnecessary abstractions, frameworks or infrastructure.

### 4.2 Representing a Task: Options Considered

| Design | Pros | Cons | Verdict |
|---|---|---|---|
| Persistent LLM agent per task | Feels "agentic" | Idle LLM loops waste resources, non-deterministic, hard to bound and test | No |
| OS process per task | Strong isolation | Telethon session can't be shared; heavy; needs IPC | No |
| One asyncio.Task loop per monitor task | Simple, natural cancellation | Scheduling logic scattered; hard to cap concurrency or prevent duplicates centrally | Acceptable, weaker |
| Task = data record; central scheduler + stateless worker | One place for concurrency caps, overlap prevention, backoff, shutdown; maps to durable queue later | Slightly more code than naive loops | Recommended |

### 4.3 Three Distinct Concepts

- Agent definition: a code-registered type (`channel_monitor`) with a config schema and worker. In the MVP, a one-entry registry.
- Monitoring task: a user-created instance with config, desired state, runtime state and checkpoints.
- Execution: one run of a task with its own record and outcome.

Desired state (what the user wants: `ACTIVE`, `PAUSED`, `CANCELLED`) is separate from runtime state (what the system is doing: `STOPPED`, `WAITING`, `RUNNING`, `BACKING_OFF`, `ERRORED`).

---

## 5. Components and Boundaries

| Component | Responsibility | Uses LLM? |
|---|---|---|
| BotGateway | Bot API polling, user registry/access check, message splitting, routes slash commands and free text | No |
| Deterministic handlers | `/start`, `/help`, `/tasks`, `/pause`, `/resume`, `/cancel`, `/setllm`, `/llm`, `/link`, `/pair`, `/recipients` -- never routed through the LLM | No |
| Orchestrator | Per-chat conversation state, builds LLM context (the caller's data only), parses to commands, validates, confirms, dispatches, formats replies | Yes (parsing only) |
| LLMService | Resolves the owner's profile, enforces timeouts, per-profile concurrency and rate limits, schema repair retry, error mapping, usage counting | n/a |
| LLMProvider adapters | Translate one interface to each vendor's API | n/a |
| Validator | Semantic checks: task refs belong to the caller, channels resolvable and accessible, recipient alias belongs to the caller, limits | No |
| TaskManager | Domain rules and state machine; sole writer of config and desired state | No |
| UserService | Users, roles, LLM profiles, recipients, pairing codes | No |
| TaskRepository | Storage (memory -> SQLite): tasks, checkpoints, executions, delivery ledger | No |
| SecretStore | Stores API keys; in-memory first, encrypted at rest from M6 | No |
| Scheduler | Tick loop, due-task selection, in-flight guard, caps, backoff, jitter, graceful shutdown | No |
| ChannelMonitorWorker | One execution against an immutable config snapshot | Indirectly |
| SessionManager | Owns the Telethon client: connect, reconnect, FloodWait handling, global MTProto rate limit, disconnect | No |
| PostDiscovery (ChannelSource) | Fetch posts newer than a checkpoint; normalize albums, text, permalink | No |
| RelevanceService | Filters -> keywords -> classifier (+ optional summary) | Yes |
| DeliveryService | Format, idempotency ledger, send through a Notifier, Bot API limits | No |

---

## 6. Multi-User and Bring-Your-Own-LLM Design

### 6.1 Users and Access

- User registry with numeric Telegram user ID. Roles: `admin`, `user`.
- Admins approve users (allowlist or invite). Unknown Telegram IDs get no response (logged).
- Every TaskManager operation is scoped by `owner_id`. The orchestrator context lists only the caller's tasks, recipient aliases and profiles.
- Per-user limits: max tasks, max channels per task, min interval, concurrent executions, daily LLM-call budget.

### 6.2 LLM Profiles

Each user registers one or more profiles:

```python
@dataclass
class LLMProfile:
    id: str
    owner_id: int
    provider: Literal["openai", "groq", "gemini", "anthropic", "ollama"]
    control_model: str        # command parsing, topic/keyword expansion
    classifier_model: str     # per-post relevance (small, cheap, fast)
    secret_ref: str           # pointer into SecretStore -- never the key itself
    schema_mode: Literal["json_schema", "json_object", "prompt_only"] = "json_schema"
    last_validated_at: datetime | None = None
```

- Resolved at execution time by `owner_id`, not baked into task config.
- Two model slots: command parsing vs. cheap classifier.
- Model names are user-supplied and never hardcoded.

### 6.3 Provider Adapters (No LangChain)

- OpenAI: `OpenAICompatibleProvider` (base URL default, `json_schema`)
- Groq: `OpenAICompatibleProvider` (base URL `https://api.groq.com/openai/v1`)
- Gemini: `OpenAICompatibleProvider` (base URL `https://generativelanguage.googleapis.com/v1beta/openai/`)
- Anthropic: `AnthropicProvider` (native, forced tool call)
- Ollama: `OllamaProvider` (native format schema)

Common interface:

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self,
        *,
        system: str,
        messages: list[Message],
        schema: type[T],
        model: str,
        options: LLMOptions,
    ) -> T: ...

    async def generate_text(
        self,
        *,
        system: str,
        messages: list[Message],
        model: str,
        options: LLMOptions,
    ) -> str: ...

    async def validate_credentials(self, model: str) -> None: ...
```

---

## 7. Telegram Integration

### 7.1 Separation of Responsibilities

- **Telegram Bot API**: Control interface, user conversational commands, notifications, delivering matches.
- **Telethon Client (User Account)**: Reading channel posts (public or joined channels).

### 7.2 Session Management

- One `TelegramClient` per account owned by exactly one process.
- Login via interactive CLI script (`scripts/login_session.py`), never through bot chat.
- Safe rate limiting on MTProto calls and FloodWaitError handling.

---

## 8. LLM Usage Policy and Orchestrator Design

### 8.1 Responsibility Split

| Use the LLM for | Use deterministic code for |
|---|---|
| Interpreting instructions into typed commands | Scheduling, retries, backoff, rate limits |
| Topic -> keyword expansion (once per config change) | Validation, authorization, limits |
| Semantic relevance judgement | State transitions, checkpoints, dedupe |
| Optional short summary or "why it matched" | Status and history reports |
| Optional prose for diagnoses | Diagnosis logic (funnel-count analysis) |
| | API key capture and storage |

### 8.2 Command Schema

Closed command set:
- `CreateTask`: name, topics, channels, recipient alias, interval_seconds
- `UpdateTask`: task_ref, add_channels, remove_channels, topics, recipient, interval_seconds
- `TaskCommand`: pause_task, resume_task, cancel_task, task_status, diagnose_task
- `ListTasks`: list_tasks
- `Clarify`: question

### 8.3 Confirmation Policy

Confirmations required for:
- `create_task` (show summary: channels, recipient, interval, keywords)
- `update_task` (changing recipient or channels)
- `cancel_task`

---

## 9. Post Discovery and Relevance Pipeline

Funnel architecture:
1. Fetch posts newer than checkpoint.
2. Normalize (merge albums, extract text, hash).
3. Hard filters (deterministic): service messages, empty text, min length, exclude keywords, exact duplicate text hash.
4. Keyword prefilter: terms generated during task creation. If no match, drop immediately (zero LLM calls).
5. LLM classifier: only evaluates surviving posts with strict JSON schema.
6. Deduplication and delivery: reserve ledger key, deliver, finalize checkpoint.

---

## 10. Data Models

Defined in `src/tgagent/domain/models.py`:
- `DesiredState`: `ACTIVE`, `PAUSED`, `CANCELLED`
- `RuntimeState`: `STOPPED`, `WAITING`, `RUNNING`, `BACKING_OFF`, `ERRORED`
- `ExecutionStatus`: `RUNNING`, `SUCCEEDED`, `PARTIAL`, `FAILED`, `CANCELLED`, `TIMED_OUT`
- `DeliveryStatus`: `PENDING`, `SENT`, `FAILED`
- `Role`: `ADMIN`, `USER`
- `User`, `UserLimits`, `Recipient`, `LLMProfile`
- `TaskConfig`, `ChannelRef`, `TaskRuntime`, `Task`
- `DiscoveredPost`, `PostDecision`, `TaskExecution`, `DeliveryRecord`
- Protocols: `TaskRepository`, `UserRepository`, `SecretStore`

---

## 11. Storage and Persistence

- Phase 1 (M1-M5): In-memory repositories implementing the protocols.
- Phase 2 (M6): SQLite repository with encrypted SecretStore (Fernet master key).
- Crash recovery: restore checkpoints, mark RUNNING executions as INTERRUPTED, reschedule next runs with jitter.

---

## 12. Scheduling and Execution Lifecycle

- Single central scheduler tick loop (~1s).
- Evaluates due tasks: desired == ACTIVE, no execution in flight, `next_run_at <= now`.
- Enforces global and per-user execution concurrency semaphores.
- Reschedules with fixed delay (interval + execution duration) plus jitter.
- Exponential backoff on transient errors up to 15 minutes.

---

## 13. Security and Reliability

- Numeric Telegram ID authorization against user registry.
- Closed command set: no arbitrary code execution, SQL generation, or shell commands.
- Post text never enters the orchestrator LLM (isolated classifier only).
- Secrets never logged, never echoed in chat, never passed into prompts.
- Structured logging with token/key redaction filter.

---

## 14. Project File Structure

```text
tg-agent/
├── pyproject.toml
├── README.md
├── .gitignore
├── .env.example
├── settings.example.toml
├── docs/
│   └── PROJECT_PLAN.md
├── scripts/
│   ├── login_session.py
│   └── gen_master_key.py
├── data/
├── src/tgagent/
│   ├── __init__.py
│   ├── __main__.py
│   ├── main.py
│   ├── config.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── commands.py
│   │   └── errors.py
│   ├── orchestrator/
│   │   ├── orchestrator.py
│   │   ├── prompts.py
│   │   ├── conversation.py
│   │   ├── validation.py
│   │   └── replies.py
│   ├── llm/
│   │   ├── base.py
│   │   ├── openai_compat.py
│   │   ├── anthropic.py
│   │   ├── ollama.py
│   │   ├── gemini_native.py
│   │   ├── factory.py
│   │   └── service.py
│   ├── users/
│   │   ├── service.py
│   │   └── recipients.py
│   ├── tasks/
│   │   ├── manager.py
│   │   ├── repository.py
│   │   ├── sqlite_repository.py
│   │   └── scheduler.py
│   ├── workers/
│   │   ├── monitor.py
│   │   └── relevance.py
│   ├── telegram/
│   │   ├── bot.py
│   │   ├── handlers.py
│   │   ├── sessions.py
│   │   ├── source.py
│   │   └── delivery.py
│   └── security/
│       ├── access.py
│       ├── secrets.py
│       └── redaction.py
└── tests/
    ├── fakes.py
    ├── golden/
    ├── unit/
    └── integration/
```

---

## 15. Technology Decisions

- Python 3.11+
- Asyncio single process event loop
- Pydantic v2
- Telegram Bot API for control & delivery
- Telethon for channel reading
- Direct provider SDKs / httpx (OpenAI, Anthropic, Groq, Gemini)
- No LangChain, no LangGraph, no Celery, no Redis, no PostgreSQL for MVP
- Fernet encryption for API keys at rest

---

## 16. Configuration Reference

Environment variables (`.env`):
- `BOT_TOKEN`: Telegram bot token
- `TG_API_ID`: Integer API ID for Telethon
- `TG_API_HASH`: API Hash string for Telethon
- `SECRETS_MASTER_KEY`: Master Fernet encryption key
- `DB_PATH`: Path to SQLite database file
- `LOG_LEVEL`: Logging verbosity

Configuration file (`settings.toml`):
- Access control (admins, require_admin_approval)
- Limits (max tasks, channels per task, concurrency, budgets)
- Scheduler tuning (tick, jitter, backoff)
- Provider base URLs

---

## 17. Testing Strategy

- Unit tests with fakes (`FakeLLM`, `FakeChannelSource`, `FakeNotifier`, `FakeClock`).
- Golden sets for parsing and relevance classification.
- Adversarial prompt injection tests.
- Redaction verification: secrets never appear in logs.

---

## 18. Development Roadmap

- **M0 Skeleton**: Skeleton package, domain models, config, redaction logging, test fakes, pytest green.
- **M1 Task Core**: TaskManager, in-memory repository, state machine.
- **M2 Scheduler**: Central scheduler, execution loops, fake clock tests.
- **M3 Control Bot**: BotGateway, user registry, admin approval, deterministic commands.
- **M4 Telegram Reading**: SessionManager, ChannelSource, Telethon reading.
- **M5 First End-to-End**: ChannelMonitorWorker, filters, keyword prefilter, delivery.
- **M6 Persistence**: SQLite repository, encrypted SecretStore, recovery.
- **M7 LLM Integration**: Multi-provider adapters, key onboarding, classifier.
- **M8 Natural-Language Orchestrator**: Conversational command parser, confirmation flow.
- **M9 Hardening**: Concurrency caps, injection tests, rate limits.
- **M10 Enhancements**: Embeddings tier, caching, multi-account.

---

## 19. Future Evolution

- PostgreSQL transition when multi-process scaling is needed.
- Durable queue seam in scheduler.
- LangGraph for multi-step agent flows.
- FastAPI for health endpoints and management dashboard.

---

## 20. Risk Register

- Restart wipes state before M6 -> Keep users informed, implement SQLite at M6.
- Telegram account ban -> Read-only, conservative intervals, no auto-join.
- Secret leaks -> Encrypted storage, redaction in all logs, deterministic input.
- LLM non-determinism -> Closed schemas, Pydantic validation, one repair retry.
- Prompt injection -> Classifier isolated from orchestrator, no tool execution.

---

## 21. Open Questions

- Reading account: Operator-owned account confirmed for MVP.
- Persistence: SQLite introduced at M6.
- Access: Admin-approved users only.
- Delivery style: Selectable per task, default immediate.
