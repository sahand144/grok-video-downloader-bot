# Universal Video Downloader Telegram Bot 🎥🤖

A Telegram bot that downloads videos from YouTube, Twitter, Instagram, TikTok, and more. Supports quality selection, inline menus, and videos larger than 50MB (sent in parts or via direct link).

---

## 🚀 Features

- Download videos from **any major platform** using `yt-dlp`
- Show **available video qualities** and let users choose
- Handles **>50MB files**: ask user to choose parts or direct download link
- Saves logs to PostgreSQL (user ID, URL, selected quality)
- Inline button menu: `/start`, `/help`, `/history`, `/clearhistory`
- Fully deployable on **Railway free tier**

---

## 🧰 Tech Stack

- Python 🐍
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- PostgreSQL
- Railway for free hosting
- `ffmpeg` via Nixpacks

---

## ⚙️ Setup & Deploy (Railway)

1. **Fork this repo & push it to GitHub**

2. **Create Railway Project**
   - Go to [Railway](https://railway.app/)
   - Create a new project and select "Deploy from GitHub"

3. **Add Environment Variables in Railway**
   - `BOT_TOKEN`: Your Telegram bot token
   - `DATABASE_URL`: Railway PostgreSQL database URL (auto-provided when you add PostgreSQL plugin)

4. **Done!** Railway builds and deploys automatically 🎉

---

## 📦 Commands

- `/start` — Show welcome and menu
- `/menu` — Show inline button menu
- `/help` — How to use
- `/history` — View recent downloads
- `/clearhistory` — Delete your download history

---

## 🧪 Run Tests

```bash
python tests.py
