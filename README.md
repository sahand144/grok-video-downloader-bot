# Telegram Video Downloader Bot

A Telegram bot to download videos, audio, and images from platforms like YouTube, Instagram, Twitter, TikTok, and Vimeo. Deployed on Railway's free tier.

## Features
- Download videos, audio, or images with quality selection.
- Persistent inline menu for commands.
- Batch URL processing.
- Progress updates and cancel option.
- History filtering and export.
- Usage stats and admin error alerts.
- Public access with rate limiting.

## Setup
1. **Create a Telegram Bot**:
   - Message `@BotFather` on Telegram, send `/newbot`, and get the bot token.
2. **Set Up Railway**:
   - Sign up at [railway.app](https://railway.app) with GitHub.
   - Create a new project and add a PostgreSQL database.
   - Copy the `DATABASE_URL` from the database variables.
3. **Deploy the Bot**:
   - Clone this repository.
   - Update `.env` with:
