"""
Instagram, TikTok & YouTube Downloader Telegram Bot
Main bot file - Multi-platform support
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from handlers import BotHandlers

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class TelegramBot:
    """Main bot class"""
    
    def __init__(self, token: str):
        if not token:
            raise ValueError("Bot token cannot be empty")
        
        self.token = token
        self.handlers = BotHandlers()
        self.application = Application.builder().token(token).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup command handlers"""
        try:
            self.application.add_handler(CommandHandler("start", self.handlers.start_command))
            self.application.add_handler(CommandHandler("fetch", self.handlers.fetch_command))
            self.application.add_handler(CommandHandler("apikey", self.handlers.apikey_command))
            self.application.add_handler(CommandHandler("history", self.handlers.history_command))
            self.application.add_handler(CallbackQueryHandler(self.handlers.handle_format_callback))
            logger.info("Bot handlers setup successfully")
        except Exception as e:
            logger.error(f"Error setting up handlers: {e}")
            raise
    
    def run(self):
        """Start the bot"""
        try:
            logger.info("Starting Multi-Platform Downloader Bot...")
            self.application.run_polling(allowed_updates=None)
        except Exception as e:
            logger.error(f"Error running bot: {e}")
            raise


def validate_environment():
    """Validate required environment variables"""
    required_vars = ["TELEGRAM_BOT_TOKEN", "API_KEY"]
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        print("❌ Error: Missing required environment variables!")
        print(f"Missing: {', '.join(missing_vars)}")
        print("\nPlease set them in your .env file or environment:")
        for var in missing_vars:
            print(f"export {var}='your_value_here'")
        print("\nSee .env.example for reference.")
        return False
    
    return True


def main():
    """Main function"""
    try:
        # Validate environment
        if not validate_environment():
            sys.exit(1)
        
        BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        
        # Create downloads directory
        downloads_dir = Path("downloads")
        downloads_dir.mkdir(exist_ok=True)
        
        # Initialize and run bot
        bot = TelegramBot(BOT_TOKEN)
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()