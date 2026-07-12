import os
import asyncio
import threading
import yt_dlp

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

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found!")

# -------------------------
# Telegram Application
# -------------------------

application = (
    Application.builder()
    .token(BOT_TOKEN)
    .request(HTTPXRequest(
        connect_timeout=30,
        read_timeout=60,
        write_timeout=60,
        pool_timeout=30,
    ))
    .build()
)

# -------------------------
# Flask (for Render)
# -------------------------

app = Flask(__name__)


@app.route("/")
def home():
    return "🤖 Instagram Reel Bot is running!"


# -------------------------
# Telegram Commands
# -------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello!\n\n"
        "Send me a public Instagram Reel link."
    )


async def instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()

    if "instagram.com" not in url:
        return

    status = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⬇️ Downloading..."
    )

    os.makedirs("downloads", exist_ok=True)

    ydl_opts = {
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "writethumbnail": True,
    }

    filename = None
    thumbnail_path = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        width = info.get("width")
        height = info.get("height")
        duration = info.get("duration")

        # yt-dlp saves the thumbnail next to the video with the same base name
        base, _ = os.path.splitext(filename)
        for ext in (".jpg", ".webp", ".png"):
            candidate = base + ext
            if os.path.exists(candidate):
                thumbnail_path = candidate
                break

        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status.message_id,
                text="📤 Uploading..."
            )
        except Exception:
            pass

        thumb_file = open(thumbnail_path, "rb") if thumbnail_path else None

        with open(filename, "rb") as video:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video,
                supports_streaming=True,
                width=width,
                height=height,
                duration=duration,
                thumbnail=thumb_file,
                read_timeout=60,
                write_timeout=60,
            )

        if thumb_file:
            thumb_file.close()

        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=status.message_id,
            )
        except Exception:
            pass

    except Exception as e:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=status.message_id,
                text=f"❌ Download failed.\n\n{e}",
            )
        except Exception:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ Download failed.\n\n{e}",
            )

    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)
        if thumbnail_path and os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)


# -------------------------
# Register handlers
# -------------------------

application.add_handler(CommandHandler("start", start))
application.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, instagram)
)

# -------------------------
# Run Telegram
# -------------------------

def run_bot():
    print("🤖 Telegram Bot Started")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    application.run_polling(
        stop_signals=None,
        close_loop=False,
    )


# -------------------------
# Main
# -------------------------

if __name__ == "__main__":

    threading.Thread(
        target=run_bot,
        daemon=True,
    ).start()

    port = int(os.environ.get("PORT", 10000))

    print(f"🌍 Flask running on port {port}")

    app.run(
        host="0.0.0.0",
        port=port,
    )
