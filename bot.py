import os
import logging
import psycopg2
import re
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from yt_dlp import YoutubeDL
from dotenv import load_dotenv
import ffmpeg
import math
import uuid
from datetime import datetime, timedelta

# Enable detailed logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# Database connection
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

# Initialize database tables
def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS interactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    video_url TEXT,
                    selected_quality TEXT,
                    media_type TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS user_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    url TEXT,
                    selected_quality TEXT,
                    media_type TEXT,
                    platform TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS errors (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    error_message TEXT,
                    url TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
    logger.info("Database initialized")

# Validate URL
def validate_url(url):
    supported_platforms = [
        r"https?://(www\.)?youtube\.com",
        r"https?://(www\.)?instagram\.com",
        r"https?://(www\.)?twitter\.com",
        r"https?://(www\.)?tiktok\.com",
        r"https?://(www\.)?vimeo\.com",
    ]
    return any(re.match(pattern, url) for pattern in supported_platforms)

# Extract platform from URL
def get_platform(url):
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    elif "instagram.com" in url:
        return "instagram"
    elif "twitter.com" in url:
        return "twitter"
    elif "tiktok.com" in url:
        return "tiktok"
    elif "vimeo.com" in url:
        return "vimeo"
    return "unknown"

# Show menu with inline buttons
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    keyboard = [
        [InlineKeyboardButton("Start", callback_data="menu_start")],
        [InlineKeyboardButton("Help", callback_data="menu_help")],
        [InlineKeyboardButton("History", callback_data="menu_history")],
        [InlineKeyboardButton("Clear History", callback_data="menu_clearhistory")],
        [InlineKeyboardButton("Stats", callback_data="menu_stats")],
        [InlineKeyboardButton("Feedback", callback_data="menu_feedback")],
        [InlineKeyboardButton("Info", callback_data="menu_info")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        if query:
            await query.message.reply_text("Choose an action:", reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text("Choose an action:", reply_markup=reply_markup)
        logger.debug("Menu displayed")
    except Exception as e:
        logger.error(f"Error displaying menu: {e}")

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to VideoDownloaderBot! Send a video, audio, or image URL from any platform (e.g., YouTube, Instagram), or use the menu below."
    )
    await show_menu(update, context)
    logger.info(f"Start command by user {update.message.from_user.id}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    **VideoDownloaderBot User Guide**

    Send a URL to download videos, audio, or images from platforms like YouTube, Instagram, Twitter, etc.

    **Commands**:
    - /start: Start the bot and show the menu.
    - /help: Show this guide.
    - /menu: Display the command menu.
    - /history [platform]: View recent downloads (e.g., /history youtube).
    - /clearhistory: Delete your download history.
    - /exporthistory: Export history as a text message.
    - /stats: Show usage statistics.
    - /feedback: Send feedback to the admin.
    - /info: Show bot status.

    **Examples**:
    - Send: `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
    - Send: `/history instagram` to see Instagram downloads.
    - Send: `/exporthistory` to get a history summary.

    **Features**:
    - Choose video quality with buttons.
    - For large videos (>50 MB), select direct link or split into parts.
    - Supports batch URLs (separate with commas or newlines).
    - Cancel downloads with the "Cancel" button.
    - Filter and export download history.
    """
    await update.message.reply_text(help_text)
    await show_menu(update, context)
    logger.info(f"Help command by user {update.message.from_user.id}")

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args
    platform = args[0].lower() if args else None

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if platform:
                    cur.execute(
                        "SELECT url, selected_quality, media_type, timestamp FROM user_history WHERE user_id = %s AND platform = %s ORDER BY timestamp DESC LIMIT 10",
                        (user_id, platform)
                    )
                else:
                    cur.execute(
                        "SELECT url, selected_quality, media_type, timestamp FROM user_history WHERE user_id = %s ORDER BY timestamp DESC LIMIT 10",
                        (user_id,)
                    )
                rows = cur.fetchall()
        if rows:
            history_text = f"Your recent downloads ({platform or 'all platforms'}):\n"
            for row in rows:
                history_text += f"URL: {row[0]}\nQuality: {row[1]}\nType: {row[2]}\nTime: {row[3]}\n\n"
        else:
            history_text = f"No download history found for {platform or 'all platforms'}."
        await update.message.reply_text(history_text)
        await show_menu(update, context)
        logger.info(f"History command by user {user_id} for platform {platform or 'all'}")
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        await update.message.reply_text("Error fetching history. Please try again.")
        await show_menu(update, context)

async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM user_history WHERE user_id = %s",
                    (user_id,)
                )
                conn.commit()
                cur.execute(
                    "SELECT COUNT(*) FROM user_history WHERE user_id = %s",
                    (user_id,)
                )
                count = cur.fetchone()[0]
        if count == 0:
            await update.message.reply_text("Your history has been cleared.")
        else:
            await update.message.reply_text("Failed to clear history. Please try again.")
        await show_menu(update, context)
        logger.info(f"Clear history command by user {user_id}")
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        await update.message.reply_text("Error clearing history. Please try again.")
        await show_menu(update, context)

async def export_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT url, selected_quality, media_type, platform, timestamp FROM user_history WHERE user_id = %s ORDER BY timestamp DESC",
                    (user_id,)
                )
                rows = cur.fetchall()
        if rows:
            history_text = "Your download history:\n\n"
            for row in rows:
                history_text += f"URL: {row[0]}\nQuality: {row[1]}\nType: {row[2]}\nPlatform: {row[3]}\nTime: {row[4]}\n\n"
        else:
            history_text = "No download history found."
        await update.message.reply_text(history_text)
        await show_menu(update, context)
        logger.info(f"Export history command by user {user_id}")
    except Exception as e:
        logger.error(f"Error exporting history: {e}")
        await update.message.reply_text("Error exporting history. Please try again.")
        await show_menu(update, context)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM user_history WHERE user_id = %s",
                    (user_id,)
                )
                total_downloads = cur.fetchone()[0]
                cur.execute(
                    "SELECT platform, COUNT(*) FROM user_history WHERE user_id = %s GROUP BY platform",
                    (user_id,)
                )
                platform_counts = cur.fetchall()
        stats_text = f"Your stats:\nTotal Downloads: {total_downloads}\n"
        for platform, count in platform_counts:
            stats_text += f"{platform.capitalize()}: {count}\n"
        await update.message.reply_text(stats_text)
        await show_menu(update, context)
        logger.info(f"Stats command by user {user_id}")
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        await update.message.reply_text("Error fetching stats. Please try again.")
        await show_menu(update, context)

async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    feedback_text = " ".join(context.args) if context.args else ""
    if not feedback_text:
        await update.message.reply_text("Please provide feedback. Example: /feedback Great bot!")
        await show_menu(update, context)
        return
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO interactions (user_id, video_url, selected_quality) VALUES (%s, %s, %s)",
                    (user_id, "feedback", feedback_text)
                )
                conn.commit()
        if ADMIN_CHAT_ID:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"Feedback from user {user_id}:\n{feedback_text}"
            )
        await update.message.reply_text("Thank you for your feedback!")
        await show_menu(update, context)
        logger.info(f"Feedback from user {user_id}: {feedback_text}")
    except Exception as e:
        logger.error(f"Error processing feedback: {e}")
        await update.message.reply_text("Error sending feedback. Please try again.")
        await show_menu(update, context)

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uptime = datetime.now() - context.bot_data.get("start_time", datetime.now())
    info_text = f"Bot Info:\nUptime: {uptime}\nStatus: Running on Railway free tier\nVersion: 2025-04-18-v2"
    await update.message.reply_text(info_text)
    await show_menu(update, context)
    logger.info(f"Info command by user {update.message.from_user.id}")

# Handle video/audio/image URLs
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    urls = [url.strip() for url in re.split(r"[\n,]", text) if url.strip()]

    # Rate limiting: 10 downloads/hour per user
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                one_hour_ago = datetime.now() - timedelta(hours=1)
                cur.execute(
                    "SELECT COUNT(*) FROM interactions WHERE user_id = %s AND timestamp > %s",
                    (user_id, one_hour_ago)
                )
                recent_downloads = cur.fetchone()[0]
                if recent_downloads >= 10:
                    await update.message.reply_text(
                        "Rate limit exceeded. Please wait an hour before downloading more."
                    )
                    await show_menu(update, context)
                    logger.info(f"Rate limit hit for user {user_id}")
                    return
    except Exception as e:
        logger.error(f"Error checking rate limit: {e}")
        await update.message.reply_text("Error checking rate limit. Please try again.")
        await show_menu(update, context)
        return

    for url in urls:
        if not validate_url(url):
            await update.message.reply_text(
                f"Unsupported URL: {url}. Please use URLs from YouTube, Instagram, Twitter, TikTok, or Vimeo."
            )
            logger.warning(f"Unsupported URL from user {user_id}: {url}")
            continue

        platform = get_platform(url)
        request_id = str(uuid.uuid4())
        context.bot_data[request_id] = {
            "url": url,
            "user_id": user_id,
            "platform": platform,
            "cancelled": False
        }

        # Log interaction
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO interactions (user_id, video_url) VALUES (%s, %s)",
                        (user_id, url)
                    )
                    conn.commit()
            logger.debug(f"Logged interaction for user {user_id}, URL: {url}")
        except Exception as e:
            logger.error(f"Error logging interaction: {e}")

        # Fetch media info with yt-dlp
        try:
            ydl_opts = {
                "quiet": True,
                "format": "best",
                "no-check-certificate": True,
                "cookiefile": None,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "geo_bypass": True,
                "no_playlist": True,
                "retries": 3,
                "extractor_retries": 3,
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                formats = info.get("formats", [])
                title = info.get("title", "Unknown")
                duration = info.get("duration", 0)
                estimated_size = info.get("filesize", 0) / (1024 * 1024) if info.get("filesize") else "Unknown"

            # Show media details
            details_text = f"Title: {title}\nDuration: {duration//60}:{duration%60:02d} min\nEstimated Size: {estimated_size:.2f} MB (if known)"
            await update.message.reply_text(details_text)

            # Ask for media type
            keyboard = [
                [InlineKeyboardButton("Video", callback_data=f"media_video|{request_id}")],
                [InlineKeyboardButton("Audio", callback_data=f"media_audio|{request_id}")],
                [InlineKeyboardButton("Image", callback_data=f"media_image|{request_id}")],
                [InlineKeyboardButton("Cancel", callback_data=f"cancel|{request_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Select media type to download:", reply_markup=reply_markup
            )
            logger.info(f"Media type selection for user {user_id}, URL: {url}")

        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
            error_msg = f"Error processing {url}: {str(e)}. Try a different platform (e.g., Vimeo, Twitter) or a public URL."
            await update.message.reply_text(error_msg)
            try:
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO errors (user_id, error_message, url) VALUES (%s, %s, %s)",
                            (user_id, str(e), url)
                        )
                        conn.commit()
                if ADMIN_CHAT_ID:
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"Error for user {user_id}: {str(e)}\nURL: {url}"
                    )
            except Exception as db_e:
                logger.error(f"Error logging error to database: {db_e}")
            del context.bot_data[request_id]

    await show_menu(update, context)

# Handle quality selection, media type, and menu callbacks
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data.split("|")
    action = data[0]

    logger.debug(f"Received callback from user {user_id}: {query.data}")

    if action == "menu":
        command = data[1]
        logger.info(f"Processing menu command: {command} for user {user_id}")
        try:
            if command == "start":
                await query.message.reply_text(
                    "Welcome to VideoDownloaderBot! Send a video, audio, or image URL from any platform (e.g., YouTube, Instagram), or use the menu below."
                )
            elif command == "help":
                help_text = """
                **VideoDownloaderBot User Guide**

                Send a URL to download videos, audio, or images from platforms like YouTube, Instagram, Twitter, etc.

                **Commands**:
                - /start: Start the bot and show the menu.
                - /help: Show this guide.
                - /menu: Display the command menu.
                - /history [platform]: View recent downloads (e.g., /history youtube).
                - /clearhistory: Delete your download history.
                - /exporthistory: Export history as a text message.
                - /stats: Show usage statistics.
                - /feedback: Send feedback to the admin.
                - /info: Show bot status.

                **Examples**:
                - Send: `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
                - Send: `/history instagram` to see Instagram downloads.
                - Send: `/exporthistory` to get a history summary.

                **Features**:
                - Choose video quality with buttons.
                - For large videos (>50 MB), select direct link or split into parts.
                - Supports batch URLs (separate with commas or newlines).
                - Cancel downloads with the "Cancel" button.
                - Filter and export download history.
                """
                await query.message.reply_text(help_text)
            elif command == "history":
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT url, selected_quality, media_type, timestamp FROM user_history WHERE user_id = %s ORDER BY timestamp DESC LIMIT 10",
                            (user_id,)
                        )
                        rows = cur.fetchall()
                if rows:
                    history_text = "Your recent downloads:\n"
                    for row in rows:
                        history_text += f"URL: {row[0]}\nQuality: {row[1]}\nType: {row[2]}\nTime: {row[3]}\n\n"
                else:
                    history_text = "No download history found."
                await query.message.reply_text(history_text)
            elif command == "clearhistory":
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "DELETE FROM user_history WHERE user_id = %s",
                            (user_id,)
                        )
                        conn.commit()
                        cur.execute(
                            "SELECT COUNT(*) FROM user_history WHERE user_id = %s",
                            (user_id,)
                        )
                        count = cur.fetchone()[0]
                if count == 0:
                    await query.message.reply_text("Your history has been cleared.")
                else:
                    await query.message.reply_text("Failed to clear history. Please try again.")
            elif command == "stats":
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) FROM user_history WHERE user_id = %s",
                            (user_id,)
                        )
                        total_downloads = cur.fetchone()[0]
                        cur.execute(
                            "SELECT platform, COUNT(*) FROM user_history WHERE user_id = %s GROUP BY platform",
                            (user_id,)
                        )
                        platform_counts = cur.fetchall()
                stats_text = f"Your stats:\nTotal Downloads: {total_downloads}\n"
                for platform, count in platform_counts:
                    stats_text += f"{platform.capitalize()}: {count}\n"
                await query.message.reply_text(stats_text)
            elif command == "feedback":
                await query.message.reply_text(
                    "Please send feedback using: /feedback Your message"
                )
            elif command == "info":
                uptime = datetime.now() - context.bot_data.get("start_time", datetime.now())
                info_text = f"Bot Info:\nUptime: {uptime}\nStatus: Running on Railway free tier\nVersion: 2025-04-18-v2"
                await query.message.reply_text(info_text)
            await show_menu(update, context, query)
        except Exception as e:
            logger.error(f"Error processing menu command {command}: {e}")
            await query.message.reply_text("Error processing command. Please try again.")
            await show_menu(update, context, query)

    elif action == "media":
        media_type, request_id = data[1], data[2]
        if request_id not in context.bot_data:
            await query.message.reply_text("Session expired. Please send the URL again.")
            await show_menu(update, context, query)
            logger.warning(f"Session expired for request_id {request_id}")
            return

        url = context.bot_data[request_id]["url"]
        platform = context.bot_data[request_id]["platform"]

        if media_type == "video":
            try:
                ydl_opts = {
                    "quiet": True,
                    "format": "bestvideo+bestaudio/best",
                    "no-check-certificate": True,
                    "cookiefile": None,
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "geo_bypass": True,
                    "no_playlist": True,
                    "retries": 3,
                    "extractor_retries": 3,
                }
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    formats = info.get("formats", [])

                video_formats = [
                    f for f in formats
                    if f.get("vcodec") != "none" and f.get("resolution") and f.get("url")
                ]
                if not video_formats:
                    await query.message.reply_text(
                        "No downloadable video formats found. Try audio or image, or use a public URL."
                    )
                    del context.bot_data[request_id]
                    await show_menu(update, context, query)
                    logger.warning(f"No video formats for URL {url}")
                    return

                keyboard = []
                for i, f in enumerate(video_formats):
                    resolution = f.get("resolution", "Unknown")
                    format_id = f.get("format_id", str(i))
                    callback_data = f"quality|{request_id}|{format_id}|video"
                    if len(callback_data.encode('utf-8')) > 64:
                        logger.warning(f"Callback data too long for format {format_id}")
                        continue
                    keyboard.append([InlineKeyboardButton(resolution, callback_data=callback_data)])
                keyboard.append([InlineKeyboardButton("Cancel", callback_data=f"cancel|{request_id}")])

                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.message.reply_text(
                    "Select a video quality:", reply_markup=reply_markup
                )
                await show_menu(update, context, query)
                logger.info(f"Video quality selection for user {user_id}, URL: {url}")

            except Exception as e:
                logger.error(f"Error processing video {url}: {e}")
                error_msg = f"Error processing video: {str(e)}. Try audio or image, or use a public URL."
                await query.message.reply_text(error_msg)
                try:
                    with get_db_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "INSERT INTO errors (user_id, error_message, url) VALUES (%s, %s, %s)",
                                (user_id, str(e), url)
                            )
                            conn.commit()
                    if ADMIN_CHAT_ID:
                        await context.bot.send_message(
                            chat_id=ADMIN_CHAT_ID,
                            text=f"Error for user {user_id}: {str(e)}\nURL: {url}"
                        )
                except Exception as db_e:
                    logger.error(f"Error logging error to database: {db_e}")
                del context.bot_data[request_id]
                await show_menu(update, context, query)

        elif media_type == "audio":
            try:
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": "audio.%(ext)s",
                    "quiet": True,
                    "no-check-certificate": True,
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "geo_bypass": True,
                    "no_playlist": True,
                    "retries": 3,
                    "extractor_retries": 3,
                }
                start_time = time.time()
                timeout = 30  # seconds
                progress_msg = await query.message.reply_text("Downloading audio...")

                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])

                audio_file = None
                for file in os.listdir():
                    if file.startswith("audio."):
                        audio_file = file
                        break

                if not audio_file:
                    await query.message.reply_text("Error: Audio file not found.")
                    del context.bot_data[request_id]
                    await show_menu(update, context, query)
                    logger.warning(f"No audio file for URL {url}")
                    return

                if context.bot_data[request_id]["cancelled"]:
                    await query.message.reply_text("Download cancelled.")
                    os.remove(audio_file)
                    del context.bot_data[request_id]
                    await show_menu(update, context, query)
                    logger.info(f"Audio download cancelled for user {user_id}")
                    return

                file_size = os.path.getsize(audio_file) / (1024 * 1024)  # MB
                if file_size <= 50:
                    with open(audio_file, "rb") as f:
                        await query.message.reply_audio(audio=f)
                else:
                    await query.message.reply_text(
                        f"Audio size ({file_size:.2f} MB) exceeds Telegram's 50 MB limit. Use a direct link instead."
                    )

                os.remove(audio_file)

                # Log to history
                try:
                    with get_db_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "INSERT INTO user_history (user_id, url, selected_quality, media_type, platform) VALUES (%s, %s, %s, %s, %s)",
                                (user_id, url, "audio", "audio", platform)
                            )
                            cur.execute(
                                "DELETE FROM user_history WHERE user_id = %s AND id NOT IN (SELECT id FROM user_history WHERE user_id = %s ORDER BY timestamp DESC LIMIT 100)",
                                (user_id, user_id)
                            )
                            conn.commit()
                except Exception as e:
                    logger.error(f"Error logging audio history: {e}")

                await progress_msg.delete()
                await query.message.reply_text("Audio download complete!")
                del context.bot_data[request_id]
                await show_menu(update, context, query)
                logger.info(f"Audio download complete for user {user_id}, URL: {url}")

            except Exception as e:
                logger.error(f"Error downloading audio: {e}")
                await query.message.reply_text(
                    f"Error downloading audio: {str(e)}. Try a public URL."
                )
                for file in os.listdir():
                    if file.startswith("audio."):
                        os.remove(file)
                del context.bot_data[request_id]
                await show_menu(update, context, query)

        elif media_type == "image":
            try:
                ydl_opts = {
                    "write_thumbnail": True,
                    "skip_download": True,  # Only download thumbnail
                    "outtmpl": "image.%(ext)s",
                    "quiet": True,
                    "no-check-certificate": True,
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "geo_bypass": True,
                    "no_playlist": True,
                    "retries": 3,
                    "extractor_retries": 3,
                }
                start_time = time.time()
                timeout = 30  # seconds
                progress_msg = await query.message.reply_text("Downloading image...")

                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)

                image_file = None
                for file in os.listdir():
                    if file.startswith("image.") and file.endswith((".jpg", ".png", ".jpeg")):
                        image_file = file
                        break

                if not image_file:
                    await query.message.reply_text(
                        "Error: No image found. Ensure the URL is a public post with a single image (e.g., Instagram post)."
                    )
                    del context.bot_data[request_id]
                    await show_menu(update, context, query)
                    logger.warning(f"No image file for URL {url}")
                    return

                if context.bot_data[request_id]["cancelled"]:
                    await query.message.reply_text("Download cancelled.")
                    os.remove(image_file)
                    del context.bot_data[request_id]
                    await show_menu(update, context, query)
                    logger.info(f"Image download cancelled for user {user_id}")
                    return

                file_size = os.path.getsize(image_file) / (1024 * 1024)  # MB
                if file_size <= 10:  # Telegram photo limit
                    with open(image_file, "rb") as f:
                        await query.message.reply_photo(photo=f)
                else:
                    await query.message.reply_text(
                        f"Image size ({file_size:.2f} MB) exceeds Telegram's 10 MB limit."
                    )

                os.remove(image_file)

                # Log to history
                try:
                    with get_db_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "INSERT INTO user_history (user_id, url, selected_quality, media_type, platform) VALUES (%s, %s, %s, %s, %s)",
                                (user_id, url, "image", "image", platform)
                            )
                            cur.execute(
                                "DELETE FROM user_history WHERE user_id = %s AND id NOT IN (SELECT id FROM user_history WHERE user_id = %s ORDER BY timestamp DESC LIMIT 100)",
                                (user_id, user_id)
                            )
                            conn.commit()
                except Exception as e:
                    logger.error(f"Error logging image history: {e}")

                await progress_msg.delete()
                await query.message.reply_text("Image download complete!")
                del context.bot_data[request_id]
                await show_menu(update, context, query)
                logger.info(f"Image download complete for user {user_id}, URL: {url}")

            except Exception as e:
                logger.error(f"Error downloading image: {e}")
                await query.message.reply_text(
                    f"Error downloading image: {str(e)}. Ensure the URL is a public post with a single image (e.g., Instagram post)."
                )
                for file in os.listdir():
                    if file.startswith("image.") and file.endswith((".jpg", ".png", ".jpeg")):
                        os.remove(file)
                del context.bot_data[request_id]
                await show_menu(update, context, query)

    elif action == "quality":
        request_id, format_id, media_type = data[1], data[2], data[3]
        if request_id not in context.bot_data:
            await query.message.reply_text("Session expired. Please send the URL again.")
            await show_menu(update, context, query)
            logger.warning(f"Session expired for request_id {request_id}")
            return

        url = context.bot_data[request_id]["url"]
        platform = context.bot_data[request_id]["platform"]

        # Log selected quality
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE interactions SET selected_quality = %s, media_type = %s WHERE user_id = %s AND video_url = %s",
                        (format_id, media_type, user_id, url)
                    )
                    cur.execute(
                        "INSERT INTO user_history (user_id, url, selected_quality, media_type, platform) VALUES (%s, %s, %s, %s, %s)",
                        (user_id, url, format_id, media_type, platform)
                    )
                    cur.execute(
                        "DELETE FROM user_history WHERE user_id = %s AND id NOT IN (SELECT id FROM user_history WHERE user_id = %s ORDER BY timestamp DESC LIMIT 100)",
                        (user_id, user_id)
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Error logging quality selection: {e}")

        # Download video
        try:
            ydl_opts = {
                "format": format_id,
                "outtmpl": "video.%(ext)s",
                "quiet": True,
                "no-check-certificate": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "geo_bypass": True,
                "no_playlist": True,
                "retries": 3,
                "extractor_retries": 3,
            }
            start_time = time.time()
            timeout = 30  # seconds
            progress_msg = await query.message.reply_text(
                "Downloading video...",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Cancel", callback_data=f"cancel|{request_id}")]
                ])
            )

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            video_file = None
            for file in os.listdir():
                if file.startswith("video."):
                    video_file = file
                    break

            if not video_file:
                await query.message.reply_text("Error: Video file not found.")
                del context.bot_data[request_id]
                await progress_msg.delete()
                await show_menu(update, context, query)
                logger.warning(f"No video file for URL {url}")
                return

            if context.bot_data[request_id]["cancelled"]:
                await query.message.reply_text("Download cancelled.")
                os.remove(video_file)
                del context.bot_data[request_id]
                await progress_msg.delete()
                await show_menu(update, context, query)
                logger.info(f"Video download cancelled for user {user_id}")
                return

            file_size = os.path.getsize(video_file) / (1024 * 1024)  # Size in MB
            if file_size <= 50:  # Telegram bot file size limit
                with open(video_file, "rb") as f:
                    await query.message.reply_video(video=f)
                os.remove(video_file)
                await progress_msg.delete()
                await query.message.reply_text("Video download complete!")
            else:
                # Prompt for large file options
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "Direct Download Link",
                            callback_data=f"link|{request_id}|{format_id}"
                        ),
                        InlineKeyboardButton(
                            "Split into Parts",
                            callback_data=f"split|{request_id}|{format_id}"
                        ),
                        InlineKeyboardButton(
                            "Cancel",
                            callback_data=f"cancel|{request_id}"
                        ),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.message.reply_text(
                    f"Video size ({file_size:.2f} MB) exceeds Telegram's 50 MB limit. Choose an option:",
                    reply_markup=reply_markup
                )
                os.remove(video_file)
                await progress_msg.delete()

            del context.bot_data[request_id]
            await show_menu(update, context, query)
            logger.info(f"Video download complete for user {user_id}, URL: {url}")

        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            await query.message.reply_text(
                f"Error downloading video: {str(e)}. Try a lower quality or a different platform (e.g., Vimeo, Twitter)."
            )
            for file in os.listdir():
                if file.startswith("video."):
                    os.remove(file)
            try:
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO errors (user_id, error_message, url) VALUES (%s, %s, %s)",
                            (user_id, str(e), url)
                        )
                        conn.commit()
                if ADMIN_CHAT_ID:
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"Error for user {user_id}: {str(e)}\nURL: {url}"
                    )
            except Exception as db_e:
                logger.error(f"Error logging error to database: {db_e}")
            del context.bot_data[request_id]
            await progress_msg.delete()
            await show_menu(update, context, query)

    elif action == "link":
        request_id, format_id = data[1], data[2]
        if request_id not in context.bot_data:
            await query.message.reply_text("Session expired. Please send the URL again.")
            await show_menu(update, context, query)
            logger.warning(f"Session expired for request_id {request_id}")
            return

        url = context.bot_data[request_id]["url"]
        try:
            ydl_opts = {
                "quiet": True,
                "no-check-certificate": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "geo_bypass": True,
                "no_playlist": True,
                "retries": 3,
                "extractor_retries": 3,
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                for f in info.get("formats", []):
                    if f.get("format_id") == format_id:
                        await query.message.reply_text(
                            f"Download the video here:\n{f.get('url')}"
                        )
                        break
            del context.bot_data[request_id]
            await show_menu(update, context, query)
            logger.info(f"Direct link provided for user {user_id}, URL: {url}")

        except Exception as e:
            logger.error(f"Error fetching link: {e}")
            await query.message.reply_text(
                f"Error fetching download link: {str(e)}. Try a different URL."
            )
            del context.bot_data[request_id]
            await show_menu(update, context, query)

    elif action == "split":
        request_id, format_id = data[1], data[2]
        if request_id not in context.bot_data:
            await query.message.reply_text("Session expired. Please send the URL again.")
            await show_menu(update, context, query)
            logger.warning(f"Session expired for request_id {request_id}")
            return

        url = context.bot_data[request_id]["url"]
        platform = context.bot_data[request_id]["platform"]
        try:
            ydl_opts = {
                "format": format_id,
                "outtmpl": "video.%(ext)s",
                "quiet": True,
                "no-check-certificate": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "geo_bypass": True,
                "no_playlist": True,
                "retries": 3,
                "extractor_retries": 3,
            }
            start_time = time.time()
            timeout = 30  # seconds
            progress_msg = await query.message.reply_text(
                "Splitting video...",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Cancel", callback_data=f"cancel|{request_id}")]
                ])
            )

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            video_file = None
            for file in os.listdir():
                if file.startswith("video."):
                    video_file = file
                    break

            if not video_file:
                await query.message.reply_text("Error: Video file not found.")
                del context.bot_data[request_id]
                await progress_msg.delete()
                await show_menu(update, context, query)
                logger.warning(f"No video file for URL {url}")
                return

            if context.bot_data[request_id]["cancelled"]:
                await query.message.reply_text("Splitting cancelled.")
                os.remove(video_file)
                del context.bot_data[request_id]
                await progress_msg.delete()
                await show_menu(update, context, query)
                logger.info(f"Video splitting cancelled for user {user_id}")
                return

            # Split video into parts (each <50 MB)
            probe = ffmpeg.probe(video_file)
            duration = float(probe["format"]["duration"])
            file_size = os.path.getsize(video_file) / (1024 * 1024)  # Size in MB
            num_parts = math.ceil(file_size / 50)
            part_duration = duration / num_parts

            for i in range(num_parts):
                output_file = f"part_{i+1}.mp4"
                (
                    ffmpeg
                    .input(video_file, ss=i * part_duration, t=part_duration)
                    .output(output_file, c="copy", f="mp4")
                    .run(overwrite_output=True)
                )
                with open(output_file, "rb") as f:
                    await query.message.reply_video(
                        video=f, caption=f"Part {i+1} of {num_parts}"
                    )
                os.remove(output_file)

            os.remove(video_file)
            await progress_msg.delete()
            await query.message.reply_text("Video splitting complete!")
            del context.bot_data[request_id]
            await show_menu(update, context, query)
            logger.info(f"Video splitting complete for user {user_id}, URL: {url}")

        except Exception as e:
            logger.error(f"Error splitting video: {e}")
            await query.message.reply_text(
                f"Error splitting video: {str(e)}. Try a direct link or a different URL."
            )
            for file in os.listdir():
                if file.startswith("video."):
                    os.remove(file)
            try:
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO user_history (user_id, url, selected_quality, media_type, platform) VALUES (%s, %s, %s, %s, %s)",
                            (user_id, url, format_id, "video", platform)
                        )
                        cur.execute(
                            "DELETE FROM user_history WHERE user_id = %s AND id NOT IN (SELECT id FROM user_history WHERE user_id = %s ORDER BY timestamp DESC LIMIT 100)",
                            (user_id, user_id)
                        )
                        cur.execute(
                            "INSERT INTO errors (user_id, error_message, url) VALUES (%s, %s, %s)",
                            (user_id, str(e), url)
                        )
                        conn.commit()
                if ADMIN_CHAT_ID:
                    await context.bot.send_message(
                        chat_id=ADMIN_CHAT_ID,
                        text=f"Error for user {user_id}: {str(e)}\nURL: {url}"
                    )
            except Exception as db_e:
                logger.error(f"Error logging error to database: {db_e}")
            del context.bot_data[request_id]
            await progress_msg.delete()
            await show_menu(update, context, query)

    elif action == "cancel":
        request_id = data[1]
        if request_id in context.bot_data:
            context.bot_data[request_id]["cancelled"] = True
            await query.message.reply_text("Operation cancelled.")
            del context.bot_data[request_id]
            logger.info(f"Operation cancelled for user {user_id}, request_id {request_id}")
        await show_menu(update, context, query)

def main():
    # Initialize database
    try:
        init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return

    # Create the Application
    try:
        application = Application.builder().token(TOKEN).build()
    except Exception as e:
        logger.error(f"Failed to create application: {e}")
        return

    # Store start time
    application.bot_data["start_time"] = datetime.now()

    # Clear webhook to prevent conflicts
    try:
        application.bot.delete_webhook()
        logger.info("Webhook cleared to prevent conflicts")
    except Exception as e:
        logger.error(f"Error clearing webhook: {e}")
        if ADMIN_CHAT_ID:
            try:
                application.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"Error clearing webhook: {str(e)}. Multiple bot instances may be running."
                )
            except Exception as send_e:
                logger.error(f"Error sending admin alert: {send_e}")

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("clearhistory", clear_history))
    application.add_handler(CommandHandler("exporthistory", export_history))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("feedback", feedback))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("menu", show_menu))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Start the bot
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Bot started successfully")
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        if ADMIN_CHAT_ID:
            try:
                application.bot.send_message(
                    chat_id=ADMIN_CHAT_ID,
                    text=f"Error starting bot: {str(e)}. Check Railway logs."
                )
            except Exception as send_e:
                logger.error(f"Error sending admin alert: {send_e}")

if __name__ == "__main__":
    main()
