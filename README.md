# Telegram Keyword Monitor & Alert Bot

A robust, production-ready Python application built with **Telethon** that monitors specified Telegram channels in real-time, scans posts for user-defined keywords, and immediately forwards matched messages to designated Telegram recipients.

This application is ideal for tracking job opportunities, news, specific topics, or brand mentions across a large number of Telegram groups and channels.

---

## Key Features

- **Real-Time Targeted Monitoring**: Uses targeted event dispatching (`chats=...`) to only listen to configured channels, cutting unnecessary CPU and network overhead by 90%+.
- **Catch-up Processing**: Scans and processes unread messages upon startup, ensuring you never miss a match when offline.
- **Smart Keyword Matching**: Precompiled, context-aware regular expressions supporting whole-word matching, multiple languages (Unicode/Arabic/Cyrillic), and special technical keywords (`C++`, `C#`, `.NET`, `Node.js`).
- **Negative / Exclusion Keywords**: Filter out spam or unwanted posts automatically (e.g. `Unpaid`, `Internship`, `Crypto`).
- **Deduplication Engine**: Built-in SQLite database (`seen_messages.db`) ensures you never receive duplicate notifications for the same message across bot restarts or manual scans.
- **Crash-Proof Formatting & Direct Links**: Safe HTML delivery with direct, clickable links to the original post (`https://t.me/...`) and automatic 4096-character limit truncation protection.
- **Media Preservation**: Automatically attaches and forwards image flyers, PDFs, or documents attached to matched posts.
- **Multiple Recipients**: Dispatches matched posts to one or more configured Telegram users with rate-limit cushioning.
- **Channel Auto-Joiner**: Automatically joins public channels, supergroups, and private invite links with accurate Telegram `FloodWaitError` cooldown handling.
- **Docker & Cloud Ready**: Supports configuration via YAML as well as environment variable overrides (`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_PHONE`).
- **Graceful Shutdown**: Cleanly stops via `SIGINT`/`SIGTERM` or interactive terminal exit key (`ESC` or `Enter`).

---

## Directory Structure

```text
├── core/                       # Shared robust application core
│   ├── __init__.py
│   ├── client.py               # Telethon client lifecycle & entity resolution
│   ├── config.py               # YAML & environment variable configuration loader
│   ├── matcher.py              # Precompiled keyword & exclusion matcher
│   ├── notifier.py             # Crash-proof HTML alert builder & media delivery
│   ├── shutdown.py             # Signal & keyboard-driven graceful shutdown
│   └── storage.py              # SQLite seen-messages deduplication database
├── join.py                     # Script to join channels safely with flood-wait protection
├── last.py                     # Script to scan recent messages (with --limit and --force)
├── main.py                     # Main real-time monitoring and alerting bot
├── teljobs.d/                  # Configuration directory
│   ├── config.yaml.example     # Template settings and Telegram credentials
│   ├── channels.conf           # List of Telegram channels to monitor
│   ├── keywords.conf           # List of keywords to search for
│   ├── exclude_keywords.conf   # Optional list of keywords to ignore/exclude
│   └── send_to_users.conf      # List of Telegram users to receive matches
├── requirements.txt            # Python dependencies
└── .gitignore                  # Git ignore rules for session databases, .db, and configs
```

---

## Installation & Setup

### 1. Prerequisites
- **Python 3.8+**
- **Telegram API Credentials**: Obtain your `api_id` and `api_hash` from [my.telegram.org](https://my.telegram.org) under API Development Tools.

### 2. Install Dependencies
```bash
# Optional: Create and activate a virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install required packages:
pip install -r requirements.txt
```

### 3. Configuration

All configuration is located in the `teljobs.d/` directory:

1. **Telegram API Credentials**:
   Copy the example template to create your `config.yaml`:
   ```bash
   # On Windows:
   copy teljobs.d\config.yaml.example teljobs.d\config.yaml

   # On Linux/macOS:
   cp teljobs.d/config.yaml.example teljobs.d/config.yaml
   ```
   Open `teljobs.d/config.yaml` and enter your credentials:
   ```yaml
   telegram:
     api_id: 12345678               # Your integer API ID
     api_hash: "your_api_hash_here" # Your API Hash string
     phone: "+1234567890"           # Your phone number with country code
   ```
   *(Alternatively, you can export `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and `TELEGRAM_PHONE` as environment variables).*

2. **Monitored Channels (`teljobs.d/channels.conf`)**:
   Add usernames, links, or channel IDs (one per line). Lines starting with `#` are ignored:
   ```text
   @job_channel_1
   https://t.me/remote_jobs
   ```

3. **Target Keywords (`teljobs.d/keywords.conf`)**:
   Add the keywords or phrases you want to monitor (one per line):
   ```text
   Python
   C++
   .NET
   Remote
   DevOps
   ```

4. **Negative Keywords (`teljobs.d/exclude_keywords.conf`)** *(Optional)*:
   Posts containing any of these keywords will be ignored:
   ```text
   Unpaid
   Volunteer
   Internship
   ```

5. **Recipients (`teljobs.d/send_to_users.conf`)**:
   Add the Telegram usernames of recipients (one per line):
   ```text
   @my_telegram_user
   ```

---

## Usage

### 1. Join Channels (`join.py`)
Automatically joins all target channels with flood-wait protection:
```bash
python join.py
```

### 2. Run Main Monitor (`main.py`)
Starts real-time monitoring and unread catch-up:
```bash
python main.py
```
- First time: Prompts for your Telegram login confirmation code.
- Scans and alerts on unread messages received while offline.
- Listens for new messages in real-time.
- Press `ESC` (or `Enter` / `Ctrl+C`) to shut down gracefully.

### 3. Check Recent History (`last.py`)
Scan recent channel history without running the real-time listener:
```bash
# Scan the last 30 messages in all channels (default):
python last.py

# Scan custom number of messages (e.g. 50):
python last.py --limit 50

# Force re-sending alerts even if previously seen:
python last.py --limit 20 --force
```

---

## License

This project is open-source and free to use under the MIT License.
