import warnings
from urllib3.exceptions import NotOpenSSLWarning
from telegram.warnings import PTBUserWarning
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
import datetime
import json
import asyncio
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import traceback

# Suppress warnings
warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")
warnings.filterwarnings("ignore", category=PTBUserWarning)

# States for conversation handler
CHOOSING_ACTION, ADDING_REMINDER = range(2)

class CalendarBot:
    def __init__(self):
        load_dotenv()  # Load environment variables
        self.token = os.getenv('BOT_TOKEN')
        self.reminders = self.load_data('reminders.json', {})
        self.holiday_cache = {}
        self.cache_expiry = 24 * 60 * 60  # 24 hours in seconds

    def load_data(self, filename, default):
        try:
            with open(filename, 'r') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
                else:
                    return default
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def save_data(self, data, filename):
        with open(filename, 'w') as f:
            json.dump(data, f)

    def get_google_calendar_service(self):
        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        creds = None

        if os.path.exists('credentials.json'):
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                raise Exception("Google Calendar credentials not found or invalid")

        return build('calendar', 'v3', credentials=creds)

    def fetch_holidays(self, limit_to_current_year=False):
        current_time = datetime.now()
        if self.holiday_cache and current_time - self.holiday_cache['timestamp'] < timedelta(seconds=self.cache_expiry):
            holidays = self.holiday_cache['data']
        else:
            service = self.get_google_calendar_service()
            calendar_id = 'en.kh#holiday@group.v.calendar.google.com'  # ID for Cambodian holidays
            now = datetime.utcnow().isoformat() + 'Z'
            events_result = service.events().list(calendarId=calendar_id,
                                                    timeMin=now,
                                                    maxResults=100, singleEvents=True,
                                                    orderBy='startTime').execute()
            events = events_result.get('items', [])

            holidays = []
            for event in events:
                start = event['start'].get('date', event['start'].get('dateTime'))
                holidays.append({
                    'name': event['summary'],
                    'date': start[:10]  # Get only the date part
                })

            self.holiday_cache = {
                'timestamp': current_time,
                'data': holidays
            }

        if limit_to_current_year:
            current_year = str(current_time.year)
            holidays = [h for h in holidays if h['date'].startswith(current_year)]

        return holidays

    async def start(self, update, context):
        keyboard = [
            [InlineKeyboardButton("Add Reminder", callback_data='add_reminder')],
            [InlineKeyboardButton("List Reminders", callback_data='list_reminders')],
            [InlineKeyboardButton("List Holidays", callback_data='list_holidays')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            'Welcome to Calendar Notification Bot!\n'
            'What would you like to do?',
            reply_markup=reply_markup
        )
        return CHOOSING_ACTION

    async def add_reminder(self, update, context):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "Please send me the reminder description and date in this format:\n"
            "Description, YYYY-MM-DD\n"
            "Example: Birthday Party, 2024-12-25"
        )
        return ADDING_REMINDER

    async def save_reminder(self, update, context):
        text = update.message.text
        try:
            description, date_str = map(str.strip, text.split(','))
            date = datetime.strptime(date_str, '%Y-%m-%d')
            
            user_id = str(update.effective_user.id)
            if user_id not in self.reminders:
                self.reminders[user_id] = []
                
            self.reminders[user_id].append({
                'description': description,
                'date': date_str
            })
            
            self.save_data(self.reminders, 'reminders.json')
            
            await update.message.reply_text(
                f"Reminder set for {date_str}:\n{description}"
            )
        except Exception as e:
            await update.message.reply_text(
                "Invalid format. Please use: Description, YYYY-MM-DD"
            )
        return ConversationHandler.END

    async def list_reminders(self, update, context):
        query = update.callback_query
        await query.answer()
        
        user_id = str(update.effective_user.id)
        if user_id not in self.reminders or not self.reminders[user_id]:
            await query.edit_message_text("You have no reminders set.")
            return ConversationHandler.END
            
        reminder_text = "Your reminders:\n\n"
        # Sort reminders by date
        sorted_reminders = sorted(
            self.reminders[user_id],
            key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d')
        )
        
        for reminder in sorted_reminders:
            reminder_text += f"📅 {reminder['date']}: {reminder['description']}\n"
            
        await query.edit_message_text(reminder_text)
        return ConversationHandler.END

    async def list_holidays(self, update: Update, context):
        query = update.callback_query
        await query.answer()

        current_year = datetime.now().year
        holidays = self.fetch_holidays(limit_to_current_year=True)
        
        if not holidays:
            await query.edit_message_text(f"No upcoming holidays found for {current_year}.")
            return CHOOSING_ACTION
        
        today = datetime.now().date()
        upcoming_holidays = [h for h in holidays if datetime.strptime(h['date'], '%Y-%m-%d').date() >= today]
        
        if not upcoming_holidays:
            await query.edit_message_text(f"No more holidays left for {current_year}.")
            return CHOOSING_ACTION
        
        holiday_list = "\n".join([f"{h['date']}: {h['name']}" for h in upcoming_holidays])
        await query.edit_message_text(f"Upcoming holidays for {current_year}:\n\n{holiday_list}")
        return CHOOSING_ACTION

    async def check_notifications(self):
        while True:
            try:
                now = datetime.now()
                today = now.strftime('%Y-%m-%d')
                
                # Fetch holidays from Google Calendar
                holidays = self.fetch_holidays()
                
                for holiday in holidays:
                    if holiday['date'] == today:
                        for chat_id in self.reminders.keys():
                            await self.application.bot.send_message(
                                chat_id=chat_id,
                                text=f"🎉 Today is {holiday['name']}!"
                            )
                
                # Check reminders
                for user_id, user_reminders in self.reminders.items():
                    for reminder in user_reminders:
                        if reminder['date'] == today:
                            await self.application.bot.send_message(
                                chat_id=user_id,
                                text=f"⏰ Reminder: {reminder['description']}"
                            )
                
            except Exception as e:
                print(f"Error in check_notifications: {e}")
            
            # Check every hour
            await asyncio.sleep(3600)

    async def run(self):
        self.application = Application.builder().token(self.token).build()
        
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                CHOOSING_ACTION: [
                    CallbackQueryHandler(self.add_reminder, pattern='^add_reminder$'),
                    CallbackQueryHandler(self.list_reminders, pattern='^list_reminders$'),
                    CallbackQueryHandler(self.list_holidays, pattern='^list_holidays$')
                ],
                ADDING_REMINDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_reminder)],
            },
            fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)]
        )
        
        self.application.add_handler(conv_handler)
        
        # Start the notification checker in the background
        self.notification_task = asyncio.create_task(self.check_notifications())
        
        await self.application.initialize()
        await self.application.start()
        print("Bot started. Press Ctrl+C to stop.")
        
        try:
            await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            await asyncio.Event().wait()  # This will run forever until cancelled
        finally:
            await self.stop()

    async def stop(self):
        try:
            print("Stopping bot...")
            self.notification_task.cancel()
            await self.application.stop()
            await self.application.shutdown()
        except Exception as e:
            print(f"Error during shutdown: {e}")
            traceback.print_exc()

if __name__ == '__main__':
    load_dotenv()
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set")

    bot = CalendarBot(BOT_TOKEN)
    
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("Bot stopped by user")