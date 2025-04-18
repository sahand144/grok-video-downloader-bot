import os
import logging
import psycopg2
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

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Database connection
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

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
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS user_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    video_url TEXT,
                    selected_quality TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to VideoDownloaderBot! Send a video URL from any platform (e.g., YouTube, Instagram), and I'll help you download it."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send a video URL, and I'll show available qualities. Choose one, and I'll send the video or offer options for large files. Use /history to see your past downloads."
    )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT video_url, selected_quality, timestamp FROM user_history WHERE user_id = %s ORDER BY timestamp DESC LIMIT 10",
                (user_id,)
            )
            rows = cur.fetchall()
    if rows:
        history_text = "Your recent downloads:\n"
        for row in rows:
            history_text += f"URL: {row[0]}\nQuality: {row[1]}\nTime: {row[2]}\n\n"
    else:
        history_text = "No download history found."
    await update.message.reply_text(history_text)

# Handle video URLs
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    video_url = update.message.text

    # Log interaction
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO interactions (user_id, video_url) VALUES (%s, %s)",
                (user_id, video_url),
            )
            conn.commit()

    # Fetch video info with yt-dlp
    try:
        ydl_opts = {"quiet": True, "format": "best"}
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            formats = info.get("formats", [])

        # Filter video formats with resolution
        video_formats = [
            f for f in formats
            if f.get("vcodec") != "none" and f.get("resolution") and f.get("url")
        ]
        if not video_formats:
            await update.message.reply_text("No downloadable video formats found. Please try another URL.")
            return

        # Create inline buttons for quality selection
        keyboard = [
            [
                InlineKeyboardButton(
                    f.get("resolution", "Unknown"),
                    callback_data=f"quality|{video_url}|{f.get('format_id')}"
                )
            ]
            for f in video_formats
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Please select a video quality:", reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Error processing URL: {e}")
        error_msg = f"Sorry, I couldn't process that URL. Error: {str(e)}. Please try another URL."
        await update.message.reply_text(error_msg)

# Handle quality selection and large file options
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data.split("|")
    action = data[0]

    if action == "quality":
        video_url, format_id = data[1], data[2]

        # Log selected quality
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE interactions SET selected_quality = %s WHERE user_id = %s AND video_url = %s",
                    (format_id, user_id, video_url),
                )
                cur.execute(
                    "INSERT INTO user_history (user_id, video_url, selected_quality) VALUES (%s, %s, %s)",
                    (user_id, video_url, format_id),
                )
                conn.commit()

        # Download video
        try:
            ydl_opts = {
                "format": format_id,
                "outtmpl": "video.%(ext)s",
                "quiet": True,
            }
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            # Find downloaded file
            video_file = None
            for file in os.listdir():
                if file.startswith("video."):
                    video_file = file
                    break

            if not video_file:
                await query.message.reply_text("Error: Video file not found.")
                return

            file_size = os.path.getsize(video_file) / (1024 * 1024)  # Size in MB
            if file_size <= 50:  # Telegram bot file size limit
                with open(video_file, "rb") as f:
                    await query.message.reply_video(video=f)
                os.remove(video_file)
            else:
                # Prompt for large file options
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "Direct Download Link",
                            callback_data=f"link|{video_url}|{format_id}"
                        ),
                        InlineKeyboardButton(
                            "Split into Parts",
                            callback_data=f"split|{video_url}|{format_id}"
                        ),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.message.reply_text(
                    f"Video size ({file_size:.2f} MB) exceeds Telegram's 50 MB limit. Choose an option:",
                    reply_markup=reply_markup
                )
                os.remove(video_file)

        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            await query.message.reply_text(
                f"Sorry, there was an error downloading the video. Error: {str(e)}. Please try another URL."
            )

    elif action == "link":
        video_url, format_id = data[1], data[2]
        try:
            ydl_opts = {"quiet": True}
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                for f in info.get("formats", []):
                    if f.get("format_id") == format_id:
                        await query.message.reply_text(
                            f"Download the video here:\n{f.get('url')}"
                        )
                        break
        except Exception as e:
            logger.error(f"Error fetching link: {e}")
            await query.message.reply_text(
                f"Error fetching download link: {str(e)}. Please try another URL."
            )

    elif action == "split":
        video_url, format_id = data[1], data[2]
        try:
            ydl_opts = {
                "format": format_id,
                "outtmpl": "video.%(ext)s",
                "quiet": True,
            }
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            video_file = None
            for file in os.listdir():
                if file.startswith("video."):
                    video_file = file
                    break

            if not video_file:
                await query.message.reply_text("Error: Video file not found.")
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

        except Exception as e:
            logger.error(f"Error splitting video: {e}")
            await query.message.reply_text(
                f"Error splitting video: {str(e)}. Please try another URL or choose a direct link."
            )

def main():
    # Initialize database
    init_db()

    # Create the Application
    application = Application.builder().token(TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()