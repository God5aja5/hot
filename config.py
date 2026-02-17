BOT_TOKEN = "8361664065:AAEunU_ovqCiubYcrBJbJOLcEANRlrEnZMI"

ADMIN_IDS = {7265489223}

BOT_NAME = "Hotmail Inboxer"
BOT_DEV = "@BaignX"

# Thread settings
INBOXER_THREADS = 50  # Threads for Inboxer checker
XBOX_THREADS = 15     # Threads for Xbox checker (reduced to avoid rate limiting)
MAX_THREADS = 100     # Maximum allowed threads

# Line limits
MAX_LINES = 6000      # Maximum lines per check for non-admin users

# File settings
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB maximum file size

# Retry settings
MAX_RETRIES = 3       # Maximum number of retry attempts
RETRY_DELAY = 2       # Delay between retries in seconds

# Rate limiting (for Xbox checker to avoid rate limiting)
REQUEST_DELAY = 0.1   # Delay between requests in seconds (reduces rate limiting)

# Timeout settings
REQUEST_TIMEOUT = 30  # HTTP request timeout in seconds

# Progress updates
PROGRESS_UPDATE_SECONDS = 2
