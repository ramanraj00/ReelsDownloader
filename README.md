# ReelsDownloader

A Telegram bot that downloads Instagram Reels and sends them back to users. Perfect for saving your favorite reels directly to your phone via Telegram.

## Stack
- **Language:** Python 3
- **Framework / runtime:** Flask + python-telegram-bot 22.8
- **Notable libraries:** 
  - `yt-dlp` — YouTube/Instagram video downloader
  - `imageio-ffmpeg` — FFmpeg integration for video compression
  - `python-dotenv` — Environment variable management
  - `httpx` — Async HTTP client for Telegram

## How it's organized

```
.
├── bot.py              Main bot application; handles download logic, compression, Telegram API
├── requirements.txt    Python dependencies
├── .env.example        Template for environment variables
└── .gitignore          Git exclusions (venv, downloads, .env, cache)
```

**How it fits together:**

The bot runs a Flask web server (for Render deployment) in the main thread and a Telegram bot in a separate async thread. When a user sends an Instagram Reel URL:

1. The `instagram()` handler intercepts the message and validates it contains `instagram.com`
2. `yt-dlp` downloads the video to a `downloads/` folder with FFmpeg
3. If the file exceeds Telegram's 50MB limit, `compress_video()` re-encodes it using FFmpeg (downscaling, reducing quality)
4. The video is sent back via `context.bot.send_video()` with the extracted thumbnail and metadata (width, height, duration)
5. Temporary files are cleaned up

## How to run it

### Prerequisites
- Python 3.7+
- A Telegram Bot Token from [BotFather](https://t.me/botfather)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/chiraglaheru/ReelsDownloader.git
   cd ReelsDownloader
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your bot token:
   ```bash
   cp .env.example .env
   # Edit .env and replace BOT_TOKEN with your actual token
   ```

5. Run the bot:
   ```bash
   python bot.py
   ```

The bot will start the Flask server on port 10000 (or `PORT` env var) and begin polling Telegram for messages.

### Environment Variables
- `BOT_TOKEN` (required) — Your Telegram Bot API token
- `PORT` (optional) — Flask server port; defaults to 10000

## Features

- **Download Instagram Reels** — Paste any public Instagram Reel link
- **Auto-compression** — Videos exceeding 50MB are automatically compressed to fit Telegram's limit
- **Thumbnail support** — Extracts and attaches video thumbnails
- **Error handling** — Graceful failures with user feedback
- **Production-ready** — Runs on Render with Flask + polling
