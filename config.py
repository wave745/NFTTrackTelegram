import os
import logging

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("No Telegram Bot Token provided. Set the TELEGRAM_BOT_TOKEN environment variable.")

# API Keys
OPENSEA_API_KEY = os.getenv("OPENSEA_API_KEY", "")
MAGICEDEN_API_KEY = os.getenv("MAGICEDEN_API_KEY", "")

# Database Configuration
DATABASE_PATH = os.getenv("DATABASE_PATH", "nft_tracker.db")

# API URLs
OPENSEA_API_URL = "https://api.opensea.io/api/v2"
MAGICEDEN_API_URL = "https://api-mainnet.magiceden.dev/v2"

# Polling Intervals (in seconds)
DEFAULT_POLLING_INTERVAL = 60  # Default 1 minute
POLLING_INTERVALS = {
    "instant": 30,        # 30 seconds
    "10min": 600,         # 10 minutes
    "hourly": 3600        # 1 hour
}

# Rate Limiting
MAX_REQUESTS_PER_MINUTE = 20  # Maximum API requests per minute

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
logging.basicConfig(level=getattr(logging, LOG_LEVEL), format=LOG_FORMAT)
logger = logging.getLogger(__name__)
