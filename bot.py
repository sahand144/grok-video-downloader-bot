import os
import logging
import re
import asyncio
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from yt_dlp import YoutubeDL
from dotenv import load_dotenv

# Enable basic logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send a URL to download a video, audio, or image from any platform."
    )
    logger.info(f"Start command by user {update.message.from_user.id}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
    **VideoDownloaderBot**

    Send a URL to download a video, audio, or image from any platform.

    **Commands**:
    - /start: Start the bot.
    - /help: Show this guide.

    **Examples**:
    - Send: `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
    - Send: `https://x.com/nocontexthumans/status/1913049846216372505`

    After sending a URL, choose Video, Audio, or Image to download.
    """
    await update.message.reply_text(help_text)
    logger.info(f"Help command by user {update.message.from_user.id}")

# Handle URLs
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    url = update.message.text.strip()
    logger.info(f"Received URL from user {user_id}: {url}")

    # Store the URL in context for media type selection
    request_id = str(user_id) + "_" + str(int(time.time()))
    context.bot_data[request_id] = {"url": url}

    # Ask for media type
    await update.message.reply_text(
        "Select media type to download (reply with one):\n- Video\n- Audio\n- Image"
    )

# Handle media type selection
async def handle_media_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.lower().strip()
    logger.info(f"Received media type from user {user_id}: {text}")

    # Find the latest request_id for this user
    request_id = None
    for key in context.bot_data.keys():
        if key.startswith(str(user_id) + "_"):
            request_id = key
            break

    if not request_id or request_id not in context.bot_data:
        await update.message.reply_text("Session expired. Please send the URL again.")
        logger.warning(f"Session expired for user {user_id}")
        return

    url = context.bot_data[request_id]["url"]
    media_type = text

    if media_type not in ["video", "audio", "image"]:
        await update.message.reply_text("Please reply with Video, Audio, or Image.")
        return

    # Download the selected media type
    try:
        if media_type == "video":
            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": "video.%(ext)s",
                "quiet": True,
                "no-check-certificate": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "geo_bypass": True,
                "no_playlist": True,
                "retries": 3,
                "extractor_retries": 3,
            }
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            video_file = None
            for file in os.listdir():
                if file.startswith("video."):
                    video_file = file
                    break

            if not video_file:
                await update.message.reply_text("Error: Video file not found.")
                del context.bot_data[request_id]
                logger.warning(f"No video file for URL {url}")
                return

            file_size = os.path.getsize(video_file) / (1024 * 1024)  # Size in MB
            if file_size <= 50:
                with open(video_file, "rb") as f:
                    await update.message.reply_video(video=f)
                await update.message.reply_text("Video download complete!")
            else:
                await update.message.reply_text(
                    f"Video size ({file_size:.2f} MB) exceeds Telegram's 50 MB limit. Try a smaller video."
                )

            os.remove(video_file)
            del context.bot_data[request_id]
            logger.info(f"Video download complete for user {user_id}, URL: {url}")

        elif media_type == "audio":
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
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            audio_file = None
            for file in os.listdir():
                if file.startswith("audio."):
                    audio_file = file
                    break

            if not audio_file:
                await update.message.reply_text("Error: Audio file not found.")
                del context.bot_data[request_id]
                logger.warning(f"No audio file for URL {url}")
                return

            file_size = os.path.getsize(audio_file) / (1024 * 1024)  # Size in MB
            if file_size <= 50:
                with open(audio_file, "rb") as f:
                    await update.message.reply_audio(audio=f)
                await update.message.reply_text("Audio download complete!")
            else:
                await update.message.reply_text(
                    f"Audio size ({file_size:.2f} MB) exceeds Telegram's 50 MB limit. Try a smaller audio."
                )

            os.remove(audio_file)
            del context.bot_data[request_id]
            logger.info(f"Audio download complete for user {user_id}, URL: {url}")

        elif media_type == "image":
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
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            image_file = None
            for file in os.listdir():
                if file.startswith("image.") and file.endswith((".jpg", ".png", ".jpeg")):
                    image_file = file
                    break

            if not image_file:
                await update.message.reply_text(
                    "Error: No image found. Ensure the URL contains a downloadable image."
                )
                del context.bot_data[request_id]
                logger.warning(f"No image file for URL {url}")
                return

            file_size = os.path.getsize(image_file) / (1024 * 1024)  # Size in MB
            if file_size <= 10:
                with open(image_file, "rb") as f:
                    await update.message.reply_photo(photo=f)
                await update.message.reply_text("Image download complete!")
            else:
                await update.message.reply_text(
                    f"Image size ({file_size:.2f} MB) exceeds Telegram's 10 MB limit."
                )

            os.remove(image_file)
            del context.bot_data[request_id]
            logger.info(f"Image download complete for user {user_id}, URL: {url}")

    except Exception as e:
        logger.error(f"Error downloading {media_type} from {url}: {e}")
        await update.message.reply_text(
            f"Error downloading {media_type}: {str(e)}. Try a different URL."
        )
        for file in os.listdir():
            if file.startswith(("video.", "audio.", "image.")):
                os.remove(file)
        del context.bot_data[request_id]

def main():
    # Create the Application
    try:
        application = Application.builder().token(TOKEN).build()
    except Exception as e:
        logger.error(f"Failed to create application: {e}")
        return

    # Clear webhook to prevent conflicts
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(application.bot.delete_webhook())
        logger.info("Webhook cleared to prevent conflicts")
    except Exception as e:
        logger.error(f"Error clearing webhook: {e}")

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(MessageHandler(filters.Regex(r'^(video|audio|image)$'), handle_media_type))

    # Start the bot
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Bot started successfully")
    except Exception as e:
        logger.error(f"Error starting bot: {e}")

if __name__ == "__main__":
    main()
