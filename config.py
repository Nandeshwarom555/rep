"""
Configuration file for the video merger bot
"""

# Telegram Bot Token - replace with your own token or set as environment variable
TELEGRAM_BOT_TOKEN = "your_telegram_bot_token"

# Maximum file size in bytes (100MB)
MAX_FILE_SIZE = 100 * 1024 * 1024

# Temporary directory for downloads and processing
# This will be overridden by tempfile.mkdtemp() at runtime
TEMP_DIR = "/tmp/video_merger_bot"

# Default output video format
DEFAULT_OUTPUT_FORMAT = "mp4"

# Default video codec for output
DEFAULT_VIDEO_CODEC = "libx264"

# Default audio codec for output
DEFAULT_AUDIO_CODEC = "aac"
