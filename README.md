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

- Push to GitHub.
- In Railway, add a new service from your GitHub repository.
- Set environment variables in Railway’s Variables tab.
- Deploy and check logs.

## Usage
- Send a URL (e.g., `https://www.youtube.com/watch?v=dQw4w9WgXcQ`).
- Use `/menu` to access commands.
- View history with `/history youtube` or export with `/exporthistory`.
- Send feedback with `/feedback Great bot!`.

## Development
- Run tests: `python tests.py` (requires local Python setup).
- Monitor Railway logs for errors.
- Update `yt-dlp` options for new platforms.

## Limitations
- Railway free tier: 512 MB RAM, 1 GB storage, 500 hours/month.
- Some YouTube videos may require authentication (not supported).
- Telegram file size limits: 50 MB for videos/audio, 10 MB for images.
