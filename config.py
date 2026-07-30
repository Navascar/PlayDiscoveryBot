import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Admin Group Telegram Chat ID
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-1001234567890"))

# Station duration timer in seconds (5 minutes = 300 seconds)
STATION_COOLDOWN_SECONDS = int(os.getenv("STATION_COOLDOWN_SECONDS", "300"))

# Database path
DB_PATH = os.getenv("DB_PATH", "bot_data.db")
