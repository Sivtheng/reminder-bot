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
from google.auth.transport.requests import Request
import traceback
import logging
from google.oauth2 import service_account
import sys
import signal
from googleapiclient.discovery_cache.base import Cache

# Suppress warnings
warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")
warnings.filterwarnings("ignore", category=PTBUserWarning)

# States for conversation handler
CHOOSING_ACTION, ADDING_REMINDER = range(2)

def signal_handler(signum, frame):
    logger.info("Signal received. Performing cleanup...")
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class MemoryCache(Cache):
    _CACHE = {}

    def get(self, url):
        return MemoryCache._CACHE.get(url)

    def set(self, url, content):
        MemoryCache._CACHE[url] = content

class CalendarBot:
    def __init__(self):
        load_dotenv()  # Load environment variables
        self.token = os.getenv('BOT_TOKEN')
        self.reminders = self.load_data('reminders.json', {})
        self.holiday_cache = {}
        self.cache_expiry = 24 * 60 * 60  # 24 hours in seconds
        self.stop_signal = asyncio.Event()

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
            if os.environ.get('GOOGLE_CREDENTIALS'):
                logger.info("Found GOOGLE_CREDENTIALS environment variable")
                creds_info = json.loads(os.environ['GOOGLE_CREDENTIALS'])
                creds = service_account.Credentials.from_service_account_info(creds_info)
            else:
                logger.error("GOOGLE_CREDENTIALS environment variable not found")
                return None

            logger.info("Building Google Calendar service")
            return build('calendar', 'v3', credentials=creds, cache=MemoryCache())
        except json.JSONDecodeError:
            logger.error("Failed to parse GOOGLE_CREDENTIALS as JSON")
        except Exception as e:
            logger.error(f"Error in get_google_calendar_service: {str(e)}")
        
        return None

    def fetch_holidays(self, limit_to_current_year=True):
        current_time = datetime.now()
        if self.holiday_cache and current_time - self.holiday_cache['timestamp'] < timedelta(seconds=self.cache_expiry):
            logger.info("Using cached holiday data")
            holidays = self.holiday_cache['data']
        else:
            logger.info("Fetching new holiday data from Google Calendar API")
            service = self.get_google_calendar_service()
            if service is None:
                logger.error("Failed to get Google Calendar service")
                return []  # Return an empty list if the service is not available
            try:
                calendar_id = 'en.kh#holiday@group.v.calendar.google.com'  # ID for Cambodian holidays
                
                # Set time range for the current year
                year_start = datetime(current_time.year, 1, 1).isoformat() + 'Z'
                year_end = datetime(current_time.year, 12, 31).isoformat() + 'Z'
                
                events_result = service.events().list(calendarId=calendar_id,
                                                        timeMin=year_start,
                                                        timeMax=year_end,
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
                logger.info(f"Fetched {len(holidays)} holidays for the year {current_time.year}")
            except Exception as e:
                logger.error(f"Error fetching holidays: {str(e)}")
                return []
        
        return holidays

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("Start method called")
        # Reset conversation state
        context.user_data.clear()
        
        keyboard = [
            [InlineKeyboardButton("Add Reminder", callback_data='add_reminder')],
            [InlineKeyboardButton("List Reminders", callback_data='list_reminders')],
            [InlineKeyboardButton("List Holidays", callback_data='list_holidays')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            logger.info("Handling callback query in start method")
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                'Welcome to Calendar Notification Bot!\n'
                'What would you like to do?',
                reply_markup=reply_markup
            )
        else:
            logger.info("Handling message in start method")
            await update.message.reply_text(
                'Welcome to Calendar Notification Bot!\n'
                'What would you like to do?',
                reply_markup=reply_markup
            )
        return CHOOSING_ACTION

    async def add_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info("Add reminder method called")
        query = update.callback_query
        await query.edit_message_text("Please enter your reminder in the format: Description, YYYY-MM-DD")
        context.user_data['expecting_reminder'] = True

    async def save_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.user_data.get('expecting_reminder'):
            return

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
            logger.error(f"Error saving reminder: {str(e)}")
            await update.message.reply_text(
                "Invalid format. Please use: Description, YYYY-MM-DD"
            )
        finally:
            context.user_data['expecting_reminder'] = False

    async def list_reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("List reminders method called")
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

    async def list_holidays(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info("List holidays method called")
        query = update.callback_query
        await query.answer()
        
        current_time = datetime.now()
        current_year = current_time.year
        
        holidays = self.fetch_holidays()
        
        if not holidays:
            await query.edit_message_text(f"No holidays found for {current_year}.")
            return
        
        holiday_list = "\n".join([f"📅 {h['date']}: {h['name']}" for h in holidays])
        message = f"Holidays for {current_year}:\n\n{holiday_list}"
        
        if len(message) > 4096:
            # If message is too long, split it
            for i in range(0, len(message), 4096):
                await query.message.reply_text(message[i:i+4096])
        else:
            await query.edit_message_text(message)
        
        # Add a button to go back to the main menu
        keyboard = [[InlineKeyboardButton("Back to Main Menu", callback_data='start')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("What would you like to do next?", reply_markup=reply_markup)

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
        
        # Start the bot
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        # Start the notification check loop after bot is initialized
        self.notification_task = asyncio.create_task(self.check_notifications())
        
        # Run the bot until it's stopped
        try:
            # Use asyncio.Event to keep the coroutine running
            stop_signal = asyncio.Event()
            await stop_signal.wait()
        finally:
            await self.application.stop()

    async def stop(self):
        try:
            print("Stopping bot...")
            self.notification_task.cancel()
            self.stop_signal.set()  # Signal the bot to stop
            await self.application.stop()
            await self.application.shutdown()
        except Exception as e:
            print(f"Error during shutdown: {e}")
            traceback.print_exc()

    def setup_handlers(self):
        logger.info("Setting up handlers")
        start_handler = CommandHandler('start', self.start)
        self.application.add_handler(start_handler)

        # Add a general callback query handler
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))

        # Add a message handler for adding reminders
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_reminder))

        logger.info("Handlers set up successfully")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        logger.info(f"Received callback query with data: {query.data}")

        await query.answer()

        if query.data == 'add_reminder':
            await self.add_reminder(update, context)
        elif query.data == 'list_reminders':
            await self.list_reminders(update, context)
        elif query.data == 'list_holidays':
            await self.list_holidays(update, context)
        elif query.data == 'start':
            await self.start(update, context)
        else:
            logger.warning(f"Unknown callback query data: {query.data}")
            await query.edit_message_text("Sorry, I didn't understand that command.")

if __name__ == '__main__':
    try:
        logger.info(f"Starting bot at {datetime.now()}")
        load_dotenv()
        BOT_TOKEN = os.getenv('BOT_TOKEN')
        
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN environment variable is not set")

        bot = CalendarBot()
        asyncio.run(bot.run())
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}", exc_info=True)
        sys.exit(1)