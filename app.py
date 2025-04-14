import os
import logging
import threading
from flask import Flask, jsonify

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key")

# Import bot here to avoid circular imports
try:
    from bot import start_bot
    bot_started = False
except ImportError as e:
    logger.error(f"Error importing bot module: {e}")
    bot_started = False

# Start the bot in a separate thread
def start_bot_thread():
    global bot_started
    if not bot_started:
        try:
            # Start the bot in a background thread
            bot_thread = threading.Thread(target=start_bot, daemon=True)
            bot_thread.start()
            logger.info("Bot thread started successfully")
            bot_started = True
        except Exception as e:
            logger.error(f"Failed to start bot thread: {e}")

# Start the bot when app starts
if os.environ.get("TELEGRAM_BOT_TOKEN"):
    start_bot_thread()
else:
    logger.warning("TELEGRAM_BOT_TOKEN not found in environment variables. Bot will not be started.")

@app.route('/')
def index():
    """Main page that shows information about the bot status"""
    return jsonify({
        "status": "running",
        "bot_started": bot_started,
        "has_token": bool(os.environ.get("TELEGRAM_BOT_TOKEN"))
    })

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    logger.error(f"404 error: {e}")
    return jsonify({"error": "Page not found"}), 404

@app.errorhandler(500)
def internal_server_error(e):
    logger.error(f"500 error: {e}")
    return jsonify({"error": "Internal server error"}), 500
