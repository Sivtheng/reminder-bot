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
- Google Cloud project with Calendar API enabled
- Service account with access to Google Calendar API

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/calendar-notification-bot.git
   cd calendar-notification-bot
   ```

2. Install required packages:

   ```bash
   pip install -r requirements.txt
   ```

3. Set up Google Calendar API:
   - Create a new project in the [Google Cloud Console](https://console.cloud.google.com/)
   - Enable the Google Calendar API for your project
   - Create a service account and download the JSON key
   - Grant the service account access to the necessary Google Calendar(s)

4. Set up environment variables:
   In your deployment environment (e.g., Railways), set the following variables:
   ```
   BOT_TOKEN=your_telegram_bot_token_here
   GOOGLE_CREDENTIALS={"type": "service_account", "project_id": "your_project_id", ...}
   ```
   Note: The GOOGLE_CREDENTIALS should contain the entire contents of your service account JSON key.

## Usage

1. Deploy the bot to your chosen platform (e.g., Railways, Heroku, etc.)

2. Start a conversation with your bot on Telegram by sending the `/start` command.

3. Use the inline keyboard to:
   - Add reminders
   - List reminders
   - View upcoming holidays

## Development

To run the bot locally for development:

1. Create a `.env` file in the project root and add your environment variables:

   ```bash
   BOT_TOKEN=your_telegram_bot_token_here
   GOOGLE_CREDENTIALS={"type": "service_account", "project_id": "your_project_id", ...}
   ```

2. Run the bot:

   ```bash
   python3 calendar_reminder.py
   ```

## Deployment

This bot is designed to be deployed on platforms like Railways. Make sure to set the environment variables (BOT_TOKEN and GOOGLE_CREDENTIALS) in your deployment environment.

## Acknowledgements

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) for the Telegram Bot API wrapper
- Google Calendar API for holiday information
