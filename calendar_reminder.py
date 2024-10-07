import warnings
from urllib3.exceptions import NotOpenSSLWarning
from telegram.warnings import PTBUserWarning
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, ContextTypes
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
import logging
from google.oauth2 import service_account

# Suppress warnings
warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")
warnings.filterwarnings("ignore", category=PTBUserWarning)

# States for conversation handler
CHOOSING_ACTION, ADDING_REMINDER = range(2)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        try:
            creds = None
            if os.environ.get('GOOGLE_TOKEN'):
                logger.info("Found GOOGLE_TOKEN environment variable")
                token_info = json.loads(os.environ['GOOGLE_TOKEN'])
                creds = Credentials.from_authorized_user_info(token_info, ['https://www.googleapis.com/auth/calendar.readonly'])
            elif os.environ.get('GOOGLE_CREDENTIALS'):
                logger.info("Found GOOGLE_CREDENTIALS environment variable")
                creds_info = json.loads(os.environ['GOOGLE_CREDENTIALS'])
                if 'installed' in creds_info:
                    # This is a client secret file, not a service account
                    flow = InstalledAppFlow.from_client_config(creds_info, ['https://www.googleapis.com/auth/calendar.readonly'])
                    creds = flow.run_local_server(port=0)
                else:
                    # Assume it's a service account
                    creds = service_account.Credentials.from_service_account_info(creds_info)
            else:
                logger.error("Neither GOOGLE_TOKEN nor GOOGLE_CREDENTIALS environment variable found")
                raise Exception("Google Calendar credentials not found")

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing expired credentials")
                    creds.refresh(Request())
                else:
                    logger.error("Credentials are invalid and cannot be refreshed")
                    raise Exception("Invalid credentials")

            logger.info("Building Google Calendar service")
            return build('calendar', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Error in get_google_calendar_service: {str(e)}")
            raise Exception(f"Google Calendar credentials error: {str(e)}")

    def fetch_holidays(self, limit_to_current_year=False):
        current_time = datetime.now()
        if self.holiday_cache and current_time - self.holiday_cache['timestamp'] < timedelta(seconds=self.cache_expiry):
            logger.info("Using cached holiday data")
            holidays = self.holiday_cache['data']
        else:
            logger.info("Fetching new holiday data from Google Calendar API")
            try:
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
                logger.info(f"Fetched {len(holidays)} holidays")
            except Exception as e:
                logger.error(f"Error fetching holidays: {str(e)}")
                return []

        if limit_to_current_year:
            current_year = str(current_time.year)
            holidays = [h for h in holidays if h['date'].startswith(current_year)]

        return holidays

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        # Reset conversation state
        context.user_data.clear()
        
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

    async def save_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text
        try:
            description, date_str = map(str.strip, text.split(','))
            date = datetime.strptime(date_str, '%Y-%m-%d')
            
            user_id = str(update.effective_user.id)
            if user_id not in self.reminders:
                self.reminders[user_id] = []
                
            self.reminders[user_id].append({
                'description': description,
                'date': date.strftime('%Y-%m-%d')  # Ensure consistent date format
            })
            
            self.save_data(self.reminders, 'reminders.json')
            
            await update.message.reply_text(
                f"Reminder set for {date_str}:\n{description}\n"
                f"You will be notified one day before and on the day of the reminder."
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

    async def list_holidays(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()

        current_year = datetime.now().year
        logger.info(f"Fetching holidays for {current_year}")
        holidays = self.fetch_holidays(limit_to_current_year=True)
        
        if not holidays:
            logger.warning("No holidays found")
            await query.edit_message_text(f"No upcoming holidays found for {current_year}.")
            return ConversationHandler.END
        
        today = datetime.now().date()
        upcoming_holidays = [h for h in holidays if datetime.strptime(h['date'], '%Y-%m-%d').date() >= today]
        
        if not upcoming_holidays:
            logger.info(f"No upcoming holidays for {current_year}")
            await query.edit_message_text(f"No more holidays left for {current_year}.")
            return ConversationHandler.END
        
        holiday_list = "\n".join([f"{h['date']}: {h['name']}" for h in upcoming_holidays])
        logger.info(f"Sending list of {len(upcoming_holidays)} upcoming holidays")
        await query.edit_message_text(f"Upcoming holidays for {current_year}:\n\n{holiday_list}")
        
        # Add a button to go back to the main menu
        keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("What would you like to do next?", reply_markup=reply_markup)
        
        return CHOOSING_ACTION

    async def check_notifications(self):
        while True:
            try:
                now = datetime.now()
                today = now.date()
                tomorrow = today + timedelta(days=1)
                
                # Fetch holidays
                holidays = self.fetch_holidays(limit_to_current_year=True)
                
                # Check holidays
                for holiday in holidays:
                    holiday_date = datetime.strptime(holiday['date'], '%Y-%m-%d').date()
                    if holiday_date == today or holiday_date == tomorrow:
                        await self.send_holiday_notification(holiday, holiday_date == today)
                
                # Check reminders
                for user_id, user_reminders in self.reminders.items():
                    for reminder in user_reminders:
                        reminder_date = datetime.strptime(reminder['date'], '%Y-%m-%d').date()
                        if reminder_date == today or reminder_date == tomorrow:
                            await self.send_reminder_notification(user_id, reminder, reminder_date == today)
                
            except Exception as e:
                logger.error(f"Error in check_notifications: {e}")
            
            # Check every hour
            await asyncio.sleep(3600)

    async def send_holiday_notification(self, holiday, is_today):
        message = f"🎉 {'Today' if is_today else 'Tomorrow'} is {holiday['name']}!"
        for user_id in self.reminders.keys():
            try:
                await self.application.bot.send_message(chat_id=user_id, text=message)
            except Exception as e:
                logger.error(f"Failed to send holiday notification to user {user_id}: {e}")

    async def send_reminder_notification(self, user_id, reminder, is_today):
        message = f"⏰ {'Reminder for today' if is_today else 'Reminder for tomorrow'}: {reminder['description']}"
        try:
            await self.application.bot.send_message(chat_id=user_id, text=message)
        except Exception as e:
            logger.error(f"Failed to send reminder notification to user {user_id}: {e}")

    async def run(self):
        self.application = Application.builder().token(self.token).build()
        self.setup_handlers()
        self.application.add_handler(self.conv_handler)
        
        # Start the bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        # Start the notification check loop
        asyncio.create_task(self.check_notifications())
        
        # Run the bot until the user presses Ctrl-C
        await self.application.updater.stop()
        await self.application.stop()

    async def stop(self):
        try:
            print("Stopping bot...")
            self.notification_task.cancel()
            await self.application.stop()
            await self.application.shutdown()
        except Exception as e:
            print(f"Error during shutdown: {e}")
            traceback.print_exc()

    def setup_handlers(self):
        self.conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                CHOOSING_ACTION: [
                    CallbackQueryHandler(self.add_reminder, pattern='^add_reminder$'),
                    CallbackQueryHandler(self.list_reminders, pattern='^list_reminders$'),
                    CallbackQueryHandler(self.list_holidays, pattern='^list_holidays$'),
                    CallbackQueryHandler(self.start, pattern='^start$'),  # Handle 'Back to Main Menu'
                ],
                ADDING_REMINDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_reminder)],
            },
            fallbacks=[CommandHandler('start', self.start)],
        )

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