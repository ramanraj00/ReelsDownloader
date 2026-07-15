import os
import glob
import asyncio
import logging
import threading
import subprocess
import shutil
import uuid
import json
import httpx
import random
import yt_dlp
import imageio_ffmpeg

from flask import Flask
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

# -----------------------------------------------------------------------------
# Logging Configuration
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found!")

MAX_TELEGRAM_SIZE = 49 * 1024 * 1024
WRITABLE_COOKIES_PATH = "/tmp/cookies.txt"
_secret_cookies_path = "/etc/secrets/cookies.txt"
_local_cookies_path = "cookies.txt" # 👈 FIX 1: Added Local path

# External API Configuration (configurable via .env)
_default_apis = "https://api.cobalt.tools,https://cobalt-api.kwiatekmateusz.com"
COBALT_APIS = [api.strip() for api in os.getenv("COBALT_APIS", _default_apis).split(",") if api.strip()]

# 👈 FIX 1: Proper Cookies Loading Logic
if os.path.exists(_local_cookies_path):
    shutil.copyfile(_local_cookies_path, WRITABLE_COOKIES_PATH)
    logger.info("Loaded LOCAL cookies.txt")
elif os.path.exists(_secret_cookies_path):
    shutil.copyfile(_secret_cookies_path, WRITABLE_COOKIES_PATH)
    logger.info("Loaded SECRET cookies.txt")
else:
    logger.info("No cookies.txt found. Running completely anonymous.")

# -----------------------------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------------------------

def _find_ffprobe() -> str | None:
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffprobe_candidate = os.path.join(os.path.dirname(ffmpeg_exe), "ffprobe")
    if os.path.isfile(ffprobe_candidate): return ffprobe_candidate
    if shutil.which("ffprobe"): return shutil.which("ffprobe")
    return None

async def get_video_info(filepath: str) -> dict:
    ffprobe_exe = _find_ffprobe()
    if ffprobe_exe:
        try:
            process = await asyncio.create_subprocess_exec(
                ffprobe_exe, "-v", "quiet", "-print_format", "json",
                "-show_streams", filepath,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=30)
            data = json.loads(stdout.decode())
            streams = data.get("streams", [])
            return {
                "has_audio": any(s.get("codec_type") == "audio" for s in streams),
                "has_video": any(s.get("codec_type") == "video" for s in streams),
                "width": next((s.get("width") for s in streams if s.get("codec_type") == "video"), None),
                "height": next((s.get("height") for s in streams if s.get("codec_type") == "video"), None),
                "vcodec": next((s.get("codec_name") for s in streams if s.get("codec_type") == "video"), None),
            }
        except Exception as e:
            logger.warning("ffprobe parsing failed: %s", e)

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    try:
        process = await asyncio.create_subprocess_exec(
            ffmpeg_exe, "-i", filepath,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        stderr_text = stderr.decode()
        return {
            "has_audio": "Audio:" in stderr_text,
            "has_video": "Video:" in stderr_text,
            "width": None, "height": None,
            "vcodec": None
        }
    except Exception as e:
        logger.warning("Fallback probe failed: %s", e)
        return {"has_audio": None, "has_video": None, "width": None, "height": None, "vcodec": None}

async def optimize_video_for_telegram(input_path: str) -> str:
    output_path = input_path.rsplit(".", 1)[0] + "_optimized.mp4"
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    file_size = os.path.getsize(input_path)
    is_large = file_size > MAX_TELEGRAM_SIZE

    vf_filter = "scale='min(1280,iw)':-2" if is_large else None
    cmd = [
        ffmpeg_exe, "-y", "-i", input_path,
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "fast",
        "-crf", "26" if is_large else "24", # 👈 FIX 2: CRF 24 prevents 50MB overflow trap
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
    ]
    if vf_filter: cmd.extend(["-vf", vf_filter])
    cmd.append(output_path)

    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

    if process.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError("FFmpeg optimization failed")
    return output_path

def resolve_downloaded_file(download_dir: str, expected_path: str, info: dict) -> str:
    if os.path.exists(expected_path): return expected_path
    base, _ = os.path.splitext(expected_path)
    for ext in (".mp4", ".mkv", ".webm", ".mov"):
        if os.path.exists(base + ext): return base + ext
    if os.path.isdir(download_dir):
        for f in os.listdir(download_dir):
            if not f.endswith((".part", ".ytdl", ".tmp", ".jpg", ".webp", ".png")):
                return os.path.join(download_dir, f)
    raise FileNotFoundError("Downloaded file not found")

def needs_auth(error_msg: str) -> bool:
    msg = error_msg.lower()
    return any(k in msg for k in [
        "login", "private", "401", "403", "429",
        "rate", "checkpoint", "empty media"
    ])

# -----------------------------------------------------------------------------
# Emergency Fallback: External APIs (Layer 3)
# -----------------------------------------------------------------------------
async def download_via_external_api(url: str, download_dir: str) -> str:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    payload = {"url": url}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for instance in COBALT_APIS:
            try:
                logger.info("Layer 3: Trying Remote API fallback: %s", instance)
                resp = await client.post(instance, json=payload, headers=headers)

                if resp.status_code != 200:
                    logger.warning("API %s returned HTTP %d", instance, resp.status_code)
                    continue

                try:
                    data = resp.json()
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning("API %s returned invalid JSON: %s", instance, e)
                    continue

                if not isinstance(data, dict):
                    logger.warning("API %s returned non-dict response: %s", instance, type(data))
                    continue

                status = data.get("status")

                if status == "error":
                    logger.warning("API %s returned error: %s", instance, data.get("text"))
                    continue

                video_url = data.get("url")

                if status == "picker" and data.get("picker"):
                    picker_items = data.get("picker")
                    if isinstance(picker_items, list) and len(picker_items) > 0:
                        video_url = picker_items[0].get("url")

                if video_url:
                    logger.info("Remote API success! Downloading MP4...")
                    video_resp = await client.get(video_url, follow_redirects=True, timeout=60.0)
                    video_resp.raise_for_status()

                    filename = os.path.join(download_dir, "api_download.mp4")
                    with open(filename, "wb") as f:
                        for chunk in video_resp.iter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
                    return filename
            except Exception as e:
                logger.warning("API %s request failed: %s", instance, e)
                continue

    raise RuntimeError("All external API fallbacks failed.")


# -----------------------------------------------------------------------------
# Telegram Application & Flask
# -----------------------------------------------------------------------------
application = (
    Application.builder()
    .token(BOT_TOKEN)
    .request(HTTPXRequest(connect_timeout=30, read_timeout=120, write_timeout=120, pool_timeout=30))
    .build()
)

app = Flask(__name__)
@app.route("/")
def home(): return "Bot is running!"

# -----------------------------------------------------------------------------
# Telegram Handlers
# -----------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello!\n\nSend me a public Instagram Reel link.")

async def instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"YAY! Bot got a message: {update.message.text}")  # 👈 YE LINE ADD KARO
    
    if not update.message or not update.message.text: return
    # ... baaki code same

    url = update.message.text.strip()
    if "instagram.com" not in url: return
    if "?" in url: url = url.split("?")[0]

    status = await context.bot.send_message(chat_id=update.effective_chat.id, text="Downloading...")

    unique_id = uuid.uuid4().hex[:8]
    download_dir = os.path.join("downloads", unique_id)
    os.makedirs(download_dir, exist_ok=True)

    base_ydl_opts = {
        "outtmpl": os.path.join(download_dir, "%(id)s.%(ext)s"),
        "quiet": True, "noplaylist": True,
        "format": "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
        "merge_output_format": "mp4",
        "writethumbnail": True,
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "socket_timeout": 60,
        "retries": 3,
        "extractor_retries": 3,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        },
    }

    filename, thumbnail_path, width, height, duration = None, None, None, None, None

    try:
        loop = asyncio.get_running_loop()

        def download_with_opts(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                expected = ydl.prepare_filename(info)
                return resolve_downloaded_file(download_dir, expected, info), info

        async def execute_download(opts, max_retries=2):
            last_err = None
            for attempt in range(max_retries):
                try:
                    return await loop.run_in_executor(None, download_with_opts, opts)
                except Exception as e:
                    last_err = e
                    if "empty media" in str(e).lower() and attempt < max_retries - 1:
                        sleep_time = random.randint(1, 3)
                        logger.info("Empty media response. Waiting %d seconds before retry...", sleep_time)
                        await asyncio.sleep(sleep_time)
                    elif attempt < max_retries - 1:
                        await asyncio.sleep(1)
            raise last_err

        # Layer 1: Try Local Anonymous
        try:
            logger.info("Layer 1: Local Anonymous download started for %s", url)
            filename, info = await execute_download(base_ydl_opts)
            width, height, duration = info.get("width"), info.get("height"), info.get("duration")
            logger.info("Layer 1 Succeeded!")

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            logger.warning("Layer 1 Failed: %s", error_msg)

            if needs_auth(error_msg):
                filename, info = None, None

                # Layer 2: Try Local Cookies (If Available)
                if os.path.exists(WRITABLE_COOKIES_PATH):
                    logger.info("Auth detected. Layer 2: Retrying with Cookies...")
                    cookie_opts = dict(base_ydl_opts)
                    cookie_opts["cookiefile"] = WRITABLE_COOKIES_PATH
                    try:
                        filename, info = await execute_download(cookie_opts, max_retries=1)
                        width, height, duration = info.get("width"), info.get("height"), info.get("duration")
                        logger.info("Layer 2 Succeeded!")
                    except Exception as cookie_err:
                        logger.warning("Layer 2 Failed: %s", str(cookie_err))
                else:
                    logger.info("No cookies found. Skipping Layer 2.")

                # Layer 3: Remote API Fallback (Emergency)
                if not filename:
                    logger.info("Layer 3: Rerouting to External APIs...")
                    try:
                        await context.bot.edit_message_text(
                            chat_id=update.effective_chat.id, message_id=status.message_id,
                            text="Fetching from remote servers..."
                        )
                    except Exception as edit_err:
                        logger.warning("Failed to edit msg: %s", edit_err)

                    try:
                        filename = await download_via_external_api(url, download_dir)
                        info = {}
                        logger.info("Layer 3 Succeeded!")
                    except Exception as api_err:
                        raise api_err
            else:
                raise e

        if not filename or not os.path.exists(filename):
            raise FileNotFoundError("Downloaded file is missing.")

        probe = await get_video_info(filename)
        vcodec = probe.get("vcodec")
        if not width and probe.get("width"): width = probe["width"]
        if not height and probe.get("height"): height = probe["height"]

        base, _ = os.path.splitext(filename)
        for ext in (".jpg", ".webp", ".png"):
            if os.path.exists(base + ext):
                thumbnail_path = base + ext
                break

        file_size = os.path.getsize(filename)
        needs_optimization = False
        opt_reason = ""
        
        if file_size > MAX_TELEGRAM_SIZE:
            needs_optimization = True
            opt_reason = "Compressing large video..."
        elif vcodec and vcodec.lower() not in ["h264", "avc1"]:
            needs_optimization = True
            opt_reason = f"Fixing {vcodec.upper()} format for Telegram compatibility..."
            
        if needs_optimization:
            try:
                await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status.message_id, text=opt_reason)
            except Exception as e:
                logger.warning("Edit msg failed: %s", e)

            try:
                optimized_path = await optimize_video_for_telegram(filename)
                if optimized_path != filename:
                    try: os.remove(filename)
                    except OSError: pass
                filename = optimized_path
            except Exception as e:
                logger.error("Optimization failed: %s", e)

        try:
            await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status.message_id, text="Uploading...")
        except Exception as e:
            logger.warning("Edit msg failed: %s", e)

        thumb_file = open(thumbnail_path, "rb") if thumbnail_path else None
        try:
            with open(filename, "rb") as video:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id, video=video, supports_streaming=True,
                    width=width, height=height, duration=duration, thumbnail=thumb_file,
                    read_timeout=120, write_timeout=120, connect_timeout=30,
                )
        finally:
            if thumb_file: thumb_file.close()

        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=status.message_id)
        except Exception as e:
            logger.warning("Delete msg failed: %s", e)

    except asyncio.TimeoutError:
        try: await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status.message_id, text="Download timed out. Try again later.")
        except Exception: pass
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e).lower()
        if "private" in error_msg: friendly = "This reel is private. Cannot download."
        elif "404" in error_msg or "not found" in error_msg: friendly = "Reel not found or deleted."
        else: friendly = "Instagram temporarily blocked the download. Please try again in a few minutes."
        try: await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status.message_id, text=friendly)
        except Exception: pass
    except Exception as e:
        logger.error("Unexpected error in handler: %s", e)
        try: await context.bot.edit_message_text(chat_id=update.effective_chat.id, message_id=status.message_id, text="Instagram temporarily blocked the download. Please try again in a few minutes.")
        except Exception: pass
    finally:
        try: shutil.rmtree(download_dir, ignore_errors=True)
        except Exception as e: logger.warning("Cleanup failed: %s", e)

# -----------------------------------------------------------------------------
# Handlers & Main
# -----------------------------------------------------------------------------
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, instagram))

def run_bot():
    logger.info("Telegram Bot Started")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    application.run_polling(stop_signals=None, close_loop=False)

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)