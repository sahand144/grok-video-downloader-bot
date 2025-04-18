import os
import logging
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import yt_dlp
import psycopg2
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Logging setup
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Connect to PostgreSQL
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
cur = conn.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS downloads (
    user_id BIGINT,
    video_url TEXT,
    selected_quality TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")
conn.commit()


# /start and menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome! Send a video link from YouTube, TikTok, Instagram, etc.")
    await show_menu(update, context)


async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📜 History", callback_data="history")],
        [InlineKeyboardButton("🧹 Clear History", callback_data="clearhistory")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose an action:", reply_markup=reply_markup)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_menu(update, context)


# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Just send me a video link, and I’ll give you download options!")


# Handle button clicks
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "history":
        cur.execute("SELECT video_url, selected_quality FROM downloads WHERE user_id=%s ORDER BY timestamp DESC LIMIT 5", (query.from_user.id,))
        rows = cur.fetchall()
        if rows:
            message = "\n".join([f"{url} ({quality})" for url, quality in rows])
        else:
            message = "No history found."
        await query.edit_message_text(f"📜 Your recent downloads:\n{message}")

    elif query.data == "clearhistory":
        cur.execute("DELETE FROM downloads WHERE user_id=%s", (query.from_user.id,))
        conn.commit()
        await query.edit_message_text("✅ Your history has been cleared.")

    elif query.data == "help":
        await query.edit_message_text("Send me any video URL and I’ll let you choose a quality to download!")


# Handle URLs
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    user_id = update.message.from_user.id

    ydl_opts = {"quiet": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = sorted(info.get("formats", []), key=lambda f: f.get("height", 0), reverse=True)
            buttons = []
            seen = set()

            for f in formats:
                height = f.get("height")
                ext = f.get("ext")
                if not height or (height in seen):
                    continue
                seen.add(height)
                label = f"{height}p ({ext})"
                buttons.append([InlineKeyboardButton(label, callback_data=f"{url}|{f['format_id']}")])

            reply_markup = InlineKeyboardMarkup(buttons[:5])
            await update.message.reply_text("Choose video quality:", reply_markup=reply_markup)
            context.user_data["video_url"] = url
    except Exception as e:
        logger.error(str(e))
        await update.message.reply_text("❌ Failed to fetch video. Please check the link and try again.")


# Download video after quality is selected
async def quality_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        data = query.data.split("|")
        if len(data) != 2:
            return

        url, format_id = data
        user_id = query.from_user.id

        # Save interaction
        cur.execute("INSERT INTO downloads (user_id, video_url, selected_quality) VALUES (%s, %s, %s)",
                    (user_id, url, format_id))
        conn.commit()

        ydl_opts = {
            "quiet": True,
            "format": format_id,
            "outtmpl": tempfile.gettempdir() + "/%(title)s.%(ext)s"
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)

        file_size = os.path.getsize(filepath)

        if file_size < 50 * 1024 * 1024:
            await query.message.reply_video(video=open(filepath, "rb"))
        else:
            keyboard = [
                [InlineKeyboardButton("📂 Send Direct Link", url=info.get("url"))],
                [InlineKeyboardButton("🧩 Split into Parts", callback_data="split|"+filepath)]
            ]
            await query.message.reply_text("The file is too large for Telegram. Choose an option:", reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logger.error(str(e))
        await query.message.reply_text("❌ An error occurred while downloading.")


# Start the bot
if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(history|clearhistory|help)$"))
    application.add_handler(CallbackQueryHandler(quality_selected, pattern=r"^https?://.+\|.+$"))

    application.run_polling()
