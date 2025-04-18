import os
import logging
import yt_dlp
import psycopg2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          CallbackQueryHandler, ContextTypes, filters)
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Database setup
def log_download(user_id, video_url, selected_quality):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                video_url TEXT,
                selected_quality TEXT,
                timestamp TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        cur.execute("INSERT INTO logs (user_id, video_url, selected_quality) VALUES (%s, %s, %s);",
                    (user_id, video_url, selected_quality))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"DB Error: {e}")

# Start/Menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_menu(update, context, welcome=True)

async def send_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, welcome=False):
    keyboard = [[
        InlineKeyboardButton("📥 Help", callback_data='help'),
        InlineKeyboardButton("📜 History", callback_data='history')
    ], [
        InlineKeyboardButton("🗑 Clear History", callback_data='clearhistory')
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = "Welcome! Send me a video link from any platform to get started." if welcome else "Choose an option below:"
    await update.message.reply_text(message, reply_markup=reply_markup)

# Handle inline menu clicks
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'help':
        await query.edit_message_text("Send any video link (YouTube, TikTok, Twitter, etc.) and I’ll let you download it in your chosen quality. Videos >50MB will give you a link or option to split.")
    elif data == 'history':
        user_id = query.from_user.id
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT video_url, selected_quality, timestamp FROM logs WHERE user_id=%s ORDER BY timestamp DESC LIMIT 5;", (user_id,))
        rows = cur.fetchall()
        if rows:
            text = "🕘 Your recent downloads:\n\n" + "\n".join([f"- {url} ({q})" for url, q, t in rows])
        else:
            text = "You have no recent downloads."
        cur.close()
        conn.close()
        await query.edit_message_text(text)
    elif data == 'clearhistory':
        user_id = query.from_user.id
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("DELETE FROM logs WHERE user_id=%s;", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        await query.edit_message_text("✅ History cleared.")

# Handle video URL
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.message.from_user.id
    try:
        ydl_opts = {"quiet": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get("formats", [])
            video_options = [f for f in formats if f.get("vcodec") != "none"]

            buttons = []
            context.user_data['download_options'] = {}

            for f in video_options:
                height = f.get("height")
                ext = f.get("ext")
                fmt_id = f.get("format_id")
                filesize = f.get("filesize", 0)
                if height and ext and fmt_id:
                    label = f"{height}p ({ext})"
                    buttons.append([InlineKeyboardButton(label, callback_data=f"dl_{fmt_id}")])
                    context.user_data['download_options'][fmt_id] = {
                        'url': url,
                        'filesize': filesize,
                        'label': label
                    }

            if not buttons:
                await update.message.reply_text("No downloadable video found in the link.")
                return

            reply_markup = InlineKeyboardMarkup(buttons)
            await update.message.reply_text("Select a quality:", reply_markup=reply_markup)

    except Exception as e:
        logger.error(e)
        await update.message.reply_text("❌ Could not process the video. Make sure it's a valid public link.")

# Handle video download after quality selection
async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    fmt_id = query.data.split("_")[1]
    option = context.user_data['download_options'].get(fmt_id)
    user_id = query.from_user.id

    if not option:
        await query.edit_message_text("Download option expired. Please send the link again.")
        return

    url = option['url']
    filesize = option['filesize'] or 0
    label = option['label']

    filename = f"video_{user_id}.mp4"

    try:
        ydl_opts = {
            'format': fmt_id,
            'outtmpl': filename,
            'quiet': True
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        log_download(user_id, url, label)

        if os.path.getsize(filename) <= 50 * 1024 * 1024:
            await query.message.reply_video(video=open(filename, 'rb'))
        else:
            keyboard = [
                [InlineKeyboardButton("📎 Get Direct Download Link", url=f"https://transfer.sh/{filename}")]
            ]
            await query.message.reply_text("⚠️ The video is larger than 50MB. Choose an option:", reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logger.error(f"Download error: {e}")
        await query.message.reply_text("❌ Download failed. Try another quality or link.")
    finally:
        if os.path.exists(filename):
            os.remove(filename)

# Main function
async def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", send_menu))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_button, pattern='^(help|history|clearhistory)$'))
    application.add_handler(CallbackQueryHandler(download_video, pattern='^dl_'))
    await application.run_polling()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
