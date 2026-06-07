# TelJobs Configuration Directory

This directory contains all configuration files for the Telegram Job Bot.

## Files:

- **config.conf** - Main configuration file (YAML format)
  - Telegram API credentials
  - Bot settings
  - File paths
  - Logging configuration
  - Retry settings
  - Keyboard settings

- **channels.conf** - List of Telegram channels to monitor
  - One channel per line (e.g., @channelname)

- **keywords.conf** - List of keywords to match in posts
  - One keyword per line
  - Supports multiple languages

- **send_to_users.conf** - List of Telegram users to receive matched posts
  - One username per line (e.g., @username)

## How to Use:

1. Edit `config.conf` to change API credentials and settings
2. Edit `channels.conf` to add/remove channels to monitor
3. Edit `keywords.conf` to add/remove keywords to match
4. Edit `send_to_users.conf` to add/remove recipients

All changes are loaded automatically when the bot starts.
