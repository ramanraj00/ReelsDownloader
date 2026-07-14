# ReelsDownloader

A Telegram bot that downloads Instagram Reels and sends them back to users. Perfect for saving your favorite reels directly to your phone via Telegram.

--------------------------------------------------------------------------------------------

## Stack
- **Language:** Python 3
- **Framework / runtime:** Flask + python-telegram-bot 22.8
- **Notable libraries:** 
  - `yt-dlp` — YouTube/Instagram video downloader
  - `imageio-ffmpeg` — FFmpeg integration for video compression
  - `python-dotenv` — Environment variable management
  - `httpx` — Async HTTP client for Telegram and external API fallbacks

## How it's organized

```text
.
├── bot.py              Main bot application; handles download logic, fallback routing, Telegram API
├── requirements.txt    Python dependencies
├── .env.example        Template for environment variables
└── .gitignore          Git exclusions (venv, downloads, .env, cache)
How it fits together:

The bot runs a Flask web server (for Render deployment) in the main thread and a Telegram bot in a separate async thread. When a user sends an Instagram Reel URL:

1.The instagram() handler intercepts the message, validates it contains instagram.com, and strips tracking parameters (utm_source, igsh)

2.Layer 1 (Local Anonymous): yt-dlp attempts to download the video anonymously without cookies

3.Layer 2 (Local Auth): If Layer 1 fails due to an authentication or rate-limit error (403, 429, empty media response, etc.), the bot retries using cookies.txt if available

4.Layer 3 (Remote API Fallback): If both local methods fail, the request is rerouted to configurable external APIs (e.g., Cobalt) as a last resort

5.If the downloaded file exceeds Telegram's 50MB limit, optimize_video_for_telegram() re-encodes it using FFmpeg (H.264, AAC, faststart)

6.The video is sent back via context.bot.send_video() with the extracted thumbnail and metadata (width, height, duration)

7.Temporary files are cleaned up

-------------------------------------------------------------------------------------------------

Note: The cookie fallback (Layer 2) and remote API fallback (Layer 3) are only triggered for authentication-related failures. Network errors, DNS failures, and 404s fail fast without wasting time on unnecessary retries.

-----------------------------------------------------------------------------------------------

How to run it
Prerequisites
Python 3.7+
A Telegram Bot Token from BotFather

Setup
1.Clone the repository:

2.Create a virtual environment:
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

3.Install dependencies:
pip install -r requirements.txt

4.Create a .env file with your bot token:
cp .env.example .env
# Edit .env and replace BOT_TOKEN with your actual token

5.Run the bot:
python bot.py

The bot will start the Flask server on port 10000 (or PORT env var) and begin polling Telegram for messages.

Environment Variables
.BOT_TOKEN (required) — Your Telegram Bot API token
.PORT (optional) — Flask server port; defaults to 10000
.COBALT_APIS (optional) — Comma-separated list of external fallback API URLs; defaults to public Cobalt instances
-------------------------------------------------------------------------------------------------
Cookies (Optional)
For higher reliability under heavy usage, you can provide an Instagram cookies.txt file. The bot checks for cookies at /etc/secrets/cookies.txt (for Render secrets) and copies them to /tmp/cookies.txt at startup. Cookies are only used as a fallback when anonymous downloads fail due to rate limits or auth blocks.

Without cookies, the bot will still work for most public reels and will fall back to external APIs when needed.

-------------------------------------------------------------------------------------------------

Features
.3-Layer Download Architecture — Anonymous first, cookies fallback, then remote API. Maximizes uptime with zero mandatory maintenance

.Smart Tracking Removal — Strips utm_source and igsh parameters from URLs to reduce Instagram blocks

.Conditional Compression — Only re-encodes videos that exceed Telegram's 50MB limit, preserving original quality for smaller files

.Targeted Fallback Logic — Cookie and API fallbacks trigger only on auth/rate-limit errors (403, 429, empty media), not on network timeouts or 404s

.Configurable External APIs — Fallback API endpoints are configurable via COBALT_APIS env var with built-in response validation

.Thumbnail Support — Extracts and attaches video thumbnails

.Friendly Error Messages — Clear user-facing messages for private reels, deleted posts, and rate limits

.Production-ready — Runs on Render with Flask + polling

-------------------------------------------------------------------------------------------------

Privacy Note
When all local download methods fail, the bot routes the Instagram URL to external third-party APIs (configured via COBALT_APIS) to fetch the video. This means the reel URL is sent to those external servers. If this is a concern, you can disable the fallback by setting COBALT_APIS to an empty value, or self-host your own Cobalt instance.