import os
import sys
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import signal

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    logger.info("Signal received. Performing cleanup...")
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)

def main():
    try:
        logger.info(f"Starting bot at {datetime.now()}")
        
        from calendar_reminder import CalendarBot
        
        bot = CalendarBot()
        
        # Run the bot
        import asyncio
        asyncio.run(bot.run())
        
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()