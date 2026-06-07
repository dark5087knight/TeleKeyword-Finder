# Telegram Keyword Monitor & Alert Bot

A lightweight, powerful Python application built with **Telethon** that monitors specified Telegram channels in real-time, scans posts for user-defined keywords, and immediately forwards matched messages to designated Telegram users. 

This application is ideal for tracking job opportunities, news, specific topics, or brand mentions across a large number of Telegram groups and channels.

---

## Key Features

- **Real-Time Monitoring**: Instantly processes new messages from monitored channels.
- **Catch-up Processing**: Scans and processes all unread messages upon startup, ensuring you never miss a match when offline.
- **Smart Keyword Matching**: Uses regular expressions to perform case-insensitive, whole-word matching across multiple languages.
- **Multiple Recipients**: Forwards matching posts to one or more configured Telegram users.
- **Automatic Joining**: Script included to automatically join all listed channels.
- **Clean Configuration**: Separates credentials, channel lists, keywords, and recipients into plain text files.
- **No Third-Party Env Dependencies**: Runs natively using a simple YAML configuration.

---

## Directory Structure

```text
├── join.py                 # Script to automatically join all listed channels
├── last.py                 # Script to scan the last 30 messages in all channels
├── main.py                 # Main real-time monitoring and alerting bot
├── teljobs.d/              # Configuration directory
│   ├── config.yaml         # Main settings and Telegram API configuration
│   ├── channels.conf       # List of Telegram channels to monitor
│   ├── keywords.conf       # List of keywords to search for
│   └── send_to_users.conf  # List of Telegram users to receive matches
└── .gitignore              # Git ignore rules for session databases and configs
```

---

## Installation & Setup

### 1. Prerequisites
- **Python 3.8+**
- **Telegram API Credentials**: You need an `api_id` and `api_hash`. Get them from [my.telegram.org](https://my.telegram.org) by registering a developer application.

### 2. Install Dependencies
Install the required packages using:
```bash
pip install -r requirements.txt
```

### 3. Configuration

All configuration is located in the `teljobs.d/` directory:

1. **Telegram API Credentials**: 
   Open `teljobs.d/config.yaml` and enter your API credentials and phone number:
   ```yaml
   telegram:
     api_id: 1234567               # Your integer API ID
     api_hash: "your_api_hash"      # Your API Hash string
     phone: "+1234567890"          # Your phone number with country code
   ```

2. **Monitored Channels**:
   Add the public usernames or links of channels you want to monitor (one per line) in `teljobs.d/channels.conf`:
   ```text
   @channel_username1
   @channel_username2
   ```

3. **Keywords**:
   Add the keywords you want to search for (one per line) in `teljobs.d/keywords.conf`:
   ```text
   Developer
   Python
   Remote Job
   ```

4. **Recipients**:
   Add the Telegram usernames of the people who should receive the matched posts (one per line) in `teljobs.d/send_to_users.conf`:
   ```text
   @recipient_username1
   @recipient_username2
   ```

---

## Usage

### 1. Join Channels (`join.py`)
Before monitoring, you must join the target channels. You can do this automatically by running:
```bash
python join.py
```
*Note: This script resolves channel names and handles rate limiting automatically.*

### 2. Run Main Monitor (`main.py`)
To start the real-time keyword monitor:
```bash
python main.py
```
Upon startup, the script will:
1. Log in via Telethon (asking for a confirmation code if it's the first time).
2. Scan and process any **unread** messages that arrived while the bot was offline.
3. Keep running and listen for new messages in real-time.
4. Press `ESC` (or `Enter`) to shut down the script gracefully.

### 3. Check Recent History (`last.py`)
If you want to manually run a scan over the last 30 messages across all monitored channels without starting the real-time listener:
```bash
python last.py
```

---

## License

This project is open-source and free to use.
