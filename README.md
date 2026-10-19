# TeleKeyword Finder

A multi-agent Telegram monitoring system where a master agent orchestrates dedicated sub-agents to monitor channels, detect keyword matches, and forward results -- all controlled through natural Telegram chat.

---

## Architecture Overview

The system is built around a two-tier agent model:

### Upper Agent (Master)

The Upper Agent is the central controller. It manages:

- All Telegram sessions and connections
- Creation, lifecycle, and coordination of Sub-Agents
- Direct conversation with the user via Telegram chat
- Task assignment and routing

The user interacts exclusively with the Upper Agent through regular Telegram messages. There is no separate UI, CLI, or dashboard -- Telegram is the interface.

### Sub-Agents (Workers)

Each Sub-Agent is a dedicated worker created by the Upper Agent to handle a single monitoring task. A Sub-Agent:

- Receives its orders from the Upper Agent (channels to watch, keywords to match, recipients to notify)
- Monitors its assigned channels in real-time
- Detects posts matching the specified criteria
- Forwards matched posts to the designated recipients
- Reports status back to the Upper Agent

Sub-Agents are created on demand and operate independently once spawned.

---

## How It Works

1. The user opens a Telegram chat with the Upper Agent (a bot or userbot account).
2. The user sends a natural-language task, for example:

   ```
   Monitor these channels: @channel_one, @channel_two, @dev_jobs
   Look for posts about: Python developer, remote work, backend engineer
   When you find matches, send them to: @my_username
   ```

3. The Upper Agent parses the request and creates a new Sub-Agent dedicated to this task.
4. The Sub-Agent begins monitoring the specified channels, scanning every new post for the requested keywords.
5. When a match is found, the Sub-Agent forwards the post to the specified recipient(s).
6. The user can message the Upper Agent at any time to:
   - Create new monitoring tasks
   - List active tasks and their Sub-Agents
   - Modify or stop existing tasks
   - Get status reports

---

## Key Features

- **Chat-Based Control**: The entire system is operated through Telegram chat with the Upper Agent. No terminal, no config files to edit manually, no restarts needed.
- **Dynamic Task Creation**: Each monitoring request spawns a dedicated Sub-Agent. Multiple tasks can run in parallel, each watching different channels for different keywords.
- **Agent Isolation**: Sub-Agents are independent. One failing or being stopped does not affect others.
- **Real-Time Monitoring**: Sub-Agents use Telegram event handlers to detect new posts the moment they appear.
- **Smart Keyword Matching**: Context-aware matching with support for whole-word detection, multiple languages (Unicode, Arabic, Cyrillic), and special technical keywords (C++, C#, .NET, Node.js).
- **Negative Keywords**: Exclude unwanted posts automatically (e.g., filter out spam, unpaid offers, or irrelevant topics).
- **Deduplication**: Built-in message tracking ensures the same post is never forwarded twice.
- **Media Forwarding**: Matched posts with attached images, documents, or files are forwarded with their media intact.
- **Direct Links**: Every forwarded match includes a clickable link to the original post.

---

## Agent Communication Flow

```
User (Telegram Chat)
    |
    v
Upper Agent (Master)
    |
    |--- Creates ---> Sub-Agent A (watches @channel_1, @channel_2 for "Python")
    |                       |
    |                       +---> Forwards matches to @recipient_1
    |
    |--- Creates ---> Sub-Agent B (watches @news_feed for "breaking, urgent")
    |                       |
    |                       +---> Forwards matches to @recipient_2
    |
    +--- Creates ---> Sub-Agent C (watches @jobs_channel for "remote backend")
                            |
                            +---> Forwards matches to @recipient_1, @recipient_3
```

---

## Setup

### Prerequisites

- Python 3.8+
- Telegram API credentials (api_id, api_hash) from [my.telegram.org](https://my.telegram.org)
- A Telegram account for the Upper Agent to operate under

### Installation

```bash
python -m venv .venv

# Windows:
.venv\Scripts\activate

# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### Configuration

Copy and fill in the environment file:

```bash
# Windows:
copy .env.example .env

# Linux/macOS:
cp .env.example .env
```

Set your Telegram API credentials in `.env`:

```
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_PHONE=+1234567890
```

---

## Usage

Start the Upper Agent:

```bash
python main.py
```

On first launch, you will be prompted for your Telegram login code. After authentication, the Upper Agent is live and listening for your messages in Telegram.

Open your Telegram app and message the Upper Agent to start creating monitoring tasks.

---
