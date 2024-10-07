# Calendar Notification Bot

## Description

Calendar Notification Bot is a Telegram bot that helps users manage reminders and keep track of holidays. It integrates with Google Calendar to fetch holiday information and allows users to set personal reminders.

## Features

- Add personal reminders
- List personal reminders
- Automatically fetch and display holidays from Google Calendar
- Send notifications for upcoming reminders and holidays

## Prerequisites

- Python 3.7+
- Telegram Bot Token
- Google Calendar API credentials

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/calendar-notification-bot.git
   cd calendar-notification-bot
   ```

2. Install required packages:

   ```bash
   pip install python-telegram-bot google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dotenv
   ```

3. Set up environment variables:
   Create a `.env` file in the project root and add your Telegram Bot Token:

   ```bash
   BOT_TOKEN=your_telegram_bot_token_here
   ```

4. Set up Google Calendar API:
   - Create a service account in the Google Cloud Console.
   - Download the JSON key for the service account.
   - Either:
     a. Set the contents of the JSON key as the `GOOGLE_CREDENTIALS` environment variable, or
     b. Rename the JSON key file to `credentials.json` and place it in the project root directory.

## Usage

1. Run the bot:

   ```bash
   python3 calendar-reminder.py
   ```

2. Start a conversation with your bot on Telegram by sending the `/start` command.

3. Use the inline keyboard to:
   - Add reminders
   - List reminders
   - View upcoming holidays

## Acknowledgements

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) for the Telegram Bot API wrapper
- Google Calendar API for holiday information
