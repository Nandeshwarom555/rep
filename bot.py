import os
import logging
import tempfile
import threading
import time
import uuid
from pathlib import Path
import telebot
from telebot import types
import video_processor
import file_uploader

# Set up logging
logging.basicConfig(level=logging.DEBUG, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get the bot token
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("No Telegram bot token found in environment variables")
    TOKEN = "YOUR_TOKEN_HERE"  # Will be replaced by actual token

# Create bot instance
bot = telebot.TeleBot(TOKEN)

# User session storage 
user_sessions = {}

class UserSession:
    def __init__(self, user_id):
        self.user_id = user_id
        self.urls = []
        self.video_paths = []
        self.current_message_id = None
        self.temp_dir = Path(tempfile.mkdtemp())
        self.final_video_path = None
        self.progress_message_id = None
        self.status = "initialized"
        self.current_state = "waiting_for_url"  # States: waiting_for_url, waiting_for_confirmation
        
    def cleanup(self):
        """Clean up temporary files after processing"""
        import shutil
        try:
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
                logger.debug(f"Cleaned up temp directory for user {self.user_id}")
        except Exception as e:
            logger.error(f"Error cleaning up temporary files: {e}")

@bot.message_handler(commands=['start'])
def handle_start(message):
    """Handler for /start command"""
    user_id = message.from_user.id
    
    # Create new session for this user or clean up existing one
    if user_id in user_sessions:
        user_sessions[user_id].cleanup()
    user_sessions[user_id] = UserSession(user_id)
    session = user_sessions[user_id]
    session.current_state = "waiting_for_url"
    
    # Send welcome message
    bot.send_message(
        message.chat.id,
        "👋 Welcome to Video Merger Bot!\n\n"
        "Send me direct URLs to video files, and I'll merge them together.\n\n"
        "Send your first video URL to start merging."
    )

@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    """Handler for /cancel command"""
    user_id = message.from_user.id
    
    if user_id in user_sessions:
        user_sessions[user_id].cleanup()
        del user_sessions[user_id]
    
    bot.send_message(message.chat.id, "Process canceled. All temporary files have been deleted.")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    """Handler for all text messages"""
    user_id = message.from_user.id
    
    # Create a new session if one doesn't exist
    if user_id not in user_sessions:
        user_sessions[user_id] = UserSession(user_id)
    
    session = user_sessions[user_id]
    
    if session.current_state == "waiting_for_url":
        handle_url_message(message)
    else:
        # If we're not expecting a URL, inform the user
        bot.send_message(
            message.chat.id,
            "Please use the buttons below to proceed or send /cancel to start over."
        )

def handle_url_message(message):
    """Handler for URL messages when in waiting_for_url state"""
    user_id = message.from_user.id
    url = message.text.strip()
    session = user_sessions[user_id]
    
    # Send a processing message
    processing_msg = bot.send_message(message.chat.id, "🔄 Processing URL, please wait...")
    
    try:
        # Download video from URL
        video_path = video_processor.sync_download_video(url, session.temp_dir)
        if not video_path:
            bot.edit_message_text(
                "❌ Failed to download video. Please check the URL and try again.",
                chat_id=message.chat.id,
                message_id=processing_msg.message_id
            )
            return
        
        # Get video info
        video_info = video_processor.get_video_info(video_path)
        
        # Add URL and downloaded video path to session
        session.urls.append(url)
        session.video_paths.append(video_path)
        
        # Create inline keyboard markup for confirmation
        markup = types.InlineKeyboardMarkup(row_width=2)
        add_url_btn = types.InlineKeyboardButton("Add Another URL", callback_data="more")
        merge_btn = types.InlineKeyboardButton("Merge Now", callback_data="merge")
        markup.add(add_url_btn, merge_btn)
        
        # Update processing message with confirmation and buttons
        bot.edit_message_text(
            f"✅ Video #{len(session.urls)} downloaded successfully!\n\n"
            f"📊 Details:\n"
            f"▪️ Duration: {video_info['duration']:.2f} seconds\n"
            f"▪️ Resolution: {video_info['width']}x{video_info['height']}\n"
            f"▪️ Format: {video_info['format']}\n\n"
            f"What would you like to do next?",
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            reply_markup=markup
        )
        
        # Update state
        session.current_state = "waiting_for_confirmation"
        
    except Exception as e:
        logger.error(f"Error processing URL: {e}")
        bot.edit_message_text(
            f"❌ Error processing URL: {str(e)}",
            chat_id=message.chat.id,
            message_id=processing_msg.message_id
        )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """Handler for callback queries from inline keyboards"""
    user_id = call.from_user.id
    session = user_sessions.get(user_id)
    
    if not session:
        bot.answer_callback_query(call.id, "Session expired. Please start again with /start")
        bot.edit_message_text(
            "❌ Session expired. Please start again with /start",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        return
    
    # Handle "more" button
    if call.data == "more":
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "Send another video URL",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        session.current_state = "waiting_for_url"
    
    # Handle "merge" button
    elif call.data == "merge":
        bot.answer_callback_query(call.id)
        
        if len(session.video_paths) < 2:
            bot.edit_message_text(
                "❌ You need at least 2 videos to merge. Please add another video URL.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id
            )
            session.current_state = "waiting_for_url"
            return
        
        # Send a progress message
        progress_msg = bot.edit_message_text(
            "🔄 Starting video merge process...",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        session.progress_message_id = progress_msg.message_id
        
        # Start merging in a background thread to not block the bot
        threading.Thread(
            target=start_merge_process,
            args=(user_id, call.message.chat.id),
            daemon=True
        ).start()

def update_progress(chat_id, message_id, progress, stage):
    """Update the progress message with current progress percentage."""
    try:
        stage_text = "merging videos" if stage == "merging" else "uploading video"
        # Only update if progress has changed significantly (at least 1%) to avoid Telegram errors
        # for message not modified
        message_text = f"🔄 {stage_text.capitalize()}... ({progress:.1f}%)"
        try:
            bot.edit_message_text(
                message_text,
                chat_id=chat_id,
                message_id=message_id
            )
        except Exception as e:
            # Ignore 'message is not modified' errors as they're expected
            if "message is not modified" not in str(e):
                logger.error(f"Error updating progress: {e}")
    except Exception as e:
        logger.error(f"Error in update_progress function: {e}")

def start_merge_process(user_id, chat_id):
    """Start the merge process in a separate thread."""
    session = user_sessions.get(user_id)
    if not session:
        return
    
    try:
        # Update status
        session.status = "merging"
        message_id = session.progress_message_id
        
        # Inform user that merging is starting
        logger.info(f"Starting merge process for user {user_id}")
        bot.edit_message_text(
            "🔄 Analyzing videos and preparing merge...",
            chat_id=chat_id,
            message_id=message_id
        )
        
        # Check if we have enough videos
        if len(session.video_paths) < 2:
            logger.error("Not enough videos to merge")
            bot.edit_message_text(
                "❌ At least 2 videos are required for merging.",
                chat_id=chat_id,
                message_id=message_id
            )
            # Clean up
            session.cleanup()
            del user_sessions[user_id]
            return
        
        # Check if all videos exist
        for path in session.video_paths:
            if not Path(path).exists():
                logger.error(f"Video file does not exist: {path}")
                bot.edit_message_text(
                    "❌ One or more video files are missing. Please try again.",
                    chat_id=chat_id,
                    message_id=message_id
                )
                # Clean up
                session.cleanup()
                del user_sessions[user_id]
                return
        
        # Get information about each video
        try:
            videos_info = []
            total_duration = 0
            total_size_mb = 0
            
            bot.edit_message_text(
                "🔄 Analyzing videos for compatibility...",
                chat_id=chat_id,
                message_id=message_id
            )
            
            for path in session.video_paths:
                info = video_processor.get_video_info(path)
                videos_info.append(info)
                total_duration += info.get('duration', 0)
                size_mb = Path(path).stat().st_size / (1024 * 1024)
                total_size_mb += size_mb
            
            # Check for potential compatibility issues
            codecs = [info.get('codec') for info in videos_info]
            unique_codecs = set(codecs)
            
            formats_message = ""
            if len(unique_codecs) > 1:
                formats_message = f"⚠️ Multiple video formats detected ({', '.join(unique_codecs)}). Will use re-encoding for compatibility.\n\n"
            
            # Create a unique output filename
            output_filename = f"merged_video_{uuid.uuid4().hex}.mp4"
            output_path = session.temp_dir / output_filename
            
            estimated_size = total_size_mb * 0.9 if len(unique_codecs) > 1 else total_size_mb
            
            bot.edit_message_text(
                f"🎬 Starting to merge {len(session.video_paths)} videos:\n\n"
                f"⏱️ Total duration: {format_duration(total_duration)}\n"
                f"📊 Estimated output size: ~{estimated_size:.1f} MB\n\n"
                f"{formats_message}"
                f"🔄 Merging videos... (0%)",
                chat_id=chat_id,
                message_id=message_id
            )
            
            # Start the actual merge with progress updates
            logger.info(f"Merging {len(session.video_paths)} videos into {output_path}")
            
            # Use better progress tracking method with timeout and auto re-encoding
            success = video_processor.merge_videos(
                session.video_paths, 
                str(output_path),
                lambda progress: update_progress(chat_id, message_id, progress, "merging"),
                timeout=1800,  # 30 minutes max for merging
                use_reencode=(len(unique_codecs) > 1)  # Auto re-encode if multiple formats
            )
        except Exception as e:
            logger.error(f"Error analyzing videos: {e}", exc_info=True)
            bot.edit_message_text(
                f"❌ Error analyzing videos: {str(e)}\n\nPlease try again with /start",
                chat_id=chat_id,
                message_id=message_id
            )
            # Clean up
            session.cleanup()
            del user_sessions[user_id]
            return
        
        if not success:
            logger.error("Merge process failed")
            bot.edit_message_text(
                "❌ Failed to merge videos. This could be due to incompatible formats or corrupted files.\n\n"
                "Tips:\n"
                "• Try with fewer videos\n"
                "• Make sure all videos are valid and playable\n"
                "• Convert videos to the same format before merging",
                chat_id=chat_id,
                message_id=message_id
            )
            # Clean up
            session.cleanup()
            del user_sessions[user_id]
            return
        
        # Check if file exists and get its size
        if not output_path.exists():
            logger.error(f"Merged file does not exist at {output_path}")
            bot.edit_message_text(
                "❌ Failed to create merged video. Please try again.",
                chat_id=chat_id,
                message_id=message_id
            )
            # Clean up
            session.cleanup()
            del user_sessions[user_id]
            return
        
        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info(f"Merge completed. File size: {file_size_mb:.2f} MB")
        
        session.final_video_path = output_path
        
        # Update status to uploading
        session.status = "uploading"
        bot.edit_message_text(
            f"✅ Merge complete! File size: {file_size_mb:.2f} MB\n"
            f"🔄 Uploading merged video... (0%)",
            chat_id=chat_id,
            message_id=message_id
        )
        
        # Upload the merged video to file hosting
        logger.info(f"Starting upload to Gofile: {output_path}")
        upload_url = file_uploader.upload_to_gofile(
            str(output_path), 
            lambda progress: update_progress(chat_id, message_id, progress, "uploading")
        )
        
        # If primary upload fails, try fallback
        if not upload_url:
            logger.warning("Gofile upload failed, trying Catbox as fallback")
            bot.edit_message_text(
                "⚠️ Primary upload failed. Trying alternative hosting...",
                chat_id=chat_id,
                message_id=message_id
            )
            upload_url = file_uploader.upload_to_catbox(
                str(output_path),
                lambda progress: update_progress(chat_id, message_id, progress, "uploading")
            )
        
        # Send the download link to the user
        if upload_url:
            logger.info(f"Upload successful. URL: {upload_url}")
            bot.edit_message_text(
                f"✅ Video merging complete!\n\n"
                f"📊 File size: {file_size_mb:.2f} MB\n"
                f"⏱️ Duration: {format_duration(total_duration)}\n\n"
                f"📥 Download your merged video here:\n{upload_url}\n\n"
                f"⚠️ Note: The download link is temporary and may expire after some time.",
                chat_id=chat_id,
                message_id=message_id
            )
        else:
            logger.error("All upload attempts failed")
            bot.edit_message_text(
                "❌ Failed to upload the merged video. Please try again later.",
                chat_id=chat_id,
                message_id=message_id
            )
        
        # Clean up
        logger.info(f"Cleaning up session for user {user_id}")
        session.cleanup()
        del user_sessions[user_id]
        
    except Exception as e:
        logger.error(f"Error in merge process: {e}", exc_info=True)
        try:
            bot.edit_message_text(
                f"❌ Error during video processing: {str(e)}\n\nPlease try again with /start",
                chat_id=chat_id,
                message_id=message_id
            )
        except Exception:
            pass
        
        # Clean up
        if user_id in user_sessions:
            user_sessions[user_id].cleanup()
            del user_sessions[user_id]

def format_duration(seconds):
    """Format seconds into a human-readable duration (HH:MM:SS)"""
    if not seconds:
        return "0:00"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"

def start_bot():
    """Start the bot."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    if not token:
        logger.error("No valid Telegram bot token provided. Please set the TELEGRAM_BOT_TOKEN environment variable.")
        return
    
    # Update token if it was loaded from env var
    bot.token = token
    
    # Start polling
    logger.info("Starting bot polling...")
    bot.infinity_polling()
    
# Run the bot if this script is executed directly
if __name__ == "__main__":
    start_bot()
