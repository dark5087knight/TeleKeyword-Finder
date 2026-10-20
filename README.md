# TeleKeyword-Finder: Agent-Based Telegram Post Discovery & Orchestration System

An interactive conversational Telegram monitoring and post discovery system. When you launch the application, an interactive chat console opens in your terminal, allowing you to converse directly with the Upper Agent in natural language.

The Upper Agent receives your monitoring instructions, confirms task parameters, spawns dedicated Sub-Agents to monitor channels via Telethon, filters posts through a multi-stage relevance funnel, and forwards matching posts to your designated Telegram recipients.

Built as a modular Python monolith without LangChain, using direct provider adapters (OpenAI, Groq, Gemini, Anthropic, Ollama) and strict schema validation.

---

## Architectural Principles

1. **Upper Agent Interactive Console**: Chat with the master controller directly in your terminal. You can give monitoring instructions in natural language or use commands (`list`, `status`, `pause`, `resume`, `cancel`).
2. **Sub-Agent Execution Plane**: For each confirmed monitoring task, the Upper Agent spawns a Sub-Agent worker with dedicated channels, keywords, and recipients.
3. **Deterministic Execution Plane**: A central scheduler manages task executions under strict concurrency and rate limits. Tasks are stateful data records executed by reusable workers, avoiding unpredictable and expensive perpetual LLM loops.
4. **Multi-Stage Relevance Funnel**:
   - Hard filters: Service messages, minimum length, negative keyword exclusions, duplicate text hashing.
   - Keyword prefilter: Fast substring matching against keywords (drops non-matching posts without making LLM calls).
   - LLM Classifier: Evaluates surviving posts with strict JSON schema constraints.
5. **Telegram Integration**:
   - Channel Reading: Read-only Telethon user account session managed in a dedicated process loop.
   - Post Delivery: Forwards matched posts to configured Telegram recipients.

---

## Agent Communication & Execution Flow

```text
User (Interactive Terminal Chat)
    |
    v
InteractiveChat Console / Upper Agent
    |-- Conversational Parser (extracts channels, keywords, recipient)
    |-- Proposal & User Confirmation Step
    +-- Spawns Sub-Agents
            |
            v
       TaskManager (State Machine & Single Writer)
            |
            v
     TaskRepository (In-Memory -> SQLite)
            ^
            |
        Scheduler (Tick Loop, Caps, Backoff, Jitter)
            |
            v
   ChannelMonitorWorker (Sub-Agent Execution)
      |-- PostDiscovery (Telethon: read posts past checkpoint)
      |-- RelevanceFunnel (Hard Filters -> Keywords -> LLM Classifier)
      |-- DeliveryService (Forwards matches to recipient)
      +-- Checkpoint & Execution Recorder
```

---

## Interactive Console Commands

When you run the application, the Upper Agent prompt loop starts:

```text
==============================================================
TeleKeyword Finder - Upper Agent Interactive Console
==============================================================
You are now chatting with the Upper Agent.
Give the agent monitoring tasks in natural language, for example:
  "Monitor @channel1, @channel2 for Python and send them to @myuser"

Commands available:
  - list              : Show active sub-agents and their tasks
  - pause <task_id>   : Pause a sub-agent
  - resume <task_id>  : Resume a sub-agent
  - cancel <task_id>  : Cancel and remove a sub-agent
  - status <task_id>  : View sub-agent status and history
  - help              : Show help message
  - exit / quit       : Shut down the agent
--------------------------------------------------------------

You: Monitor @tech_jobs, @remote_python for backend and send them to @dev_recruiter

Upper Agent:
Upper Agent proposal:
I will spawn a Sub-Agent to monitor the following channels:
  - Channels: @tech_jobs, @remote_python
  - Keywords to watch for: backend
  - Forward matches to: @dev_recruiter
  - Check interval: 120 seconds

Should I proceed with creating this Sub-Agent? (yes / no)

You: yes

Upper Agent:
Sub-Agent 'subagent_1' spawned successfully.
It is now actively monitoring: @tech_jobs, @remote_python
Filtering for: backend
Forwarding matches to: @dev_recruiter
```

---

## Project Structure

```text
├── pyproject.toml              # Build & dependency metadata
├── README.md                   # System documentation
├── .env.example                # Environment variables template
├── settings.example.toml       # System settings & provider configurations
├── docs/
│   └── PROJECT_PLAN.md         # Complete architectural specification & roadmap
├── scripts/
│   ├── login_session.py        # CLI Telethon account login
│   └── gen_master_key.py       # Master Fernet encryption key generator
├── src/tgagent/
│   ├── __init__.py
│   ├── __main__.py             # Entry point (python -m tgagent)
│   ├── main.py                 # Composition root & interactive console runner
│   ├── config.py               # Pydantic settings & configuration loader
│   ├── domain/                 # Pure domain models, schemas, enums, errors
│   │   ├── models.py
│   │   ├── commands.py
│   │   └── errors.py
│   ├── orchestrator/           # Upper Agent conversation & interactive console
│   │   ├── __init__.py
│   │   └── interactive.py      # Console chat loop & natural language parser
│   ├── llm/                    # Provider adapters (OpenAI, Groq, Gemini, Anthropic)
│   ├── users/                  # User registry, recipient aliases, onboarding
│   ├── tasks/                  # Task manager, repository, scheduler
│   ├── workers/                # Execution worker, relevance funnel
│   ├── telegram/               # Telethon session, source, and delivery
│   └── security/               # Secret store, access control, log redaction
└── tests/
    ├── fakes.py                # Test doubles (FakeLLM, FakeClock, FakeChannelSource)
    └── unit/                   # Unit test suite
```

---

## Setup & Getting Started

### 1. Prerequisites

- Python 3.11+
- Telegram API ID and API Hash from [my.telegram.org](https://my.telegram.org)

### 2. Installation

Clone the repository and install dependencies in editable mode:

```bash
python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
pip install -e .
```

### 3. Configuration

Generate an encryption key for the secret store:

```bash
python scripts/gen_master_key.py
```

Copy configuration templates:

```bash
# Windows
copy .env.example .env
copy settings.example.toml settings.toml

# Linux/macOS
cp .env.example .env
cp settings.example.toml settings.toml
```

Fill in `.env` with your `TG_API_ID`, `TG_API_HASH`, and `SECRETS_MASTER_KEY`.

### 4. Reading Account Authentication

Authorize the Telethon reading account via interactive CLI:

```bash
python scripts/login_session.py
```

### 5. Running the Application

Launch the application to chat directly with the Upper Agent:

```bash
python -m tgagent
