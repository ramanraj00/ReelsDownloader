import os
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

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found!")

# -------------------------
# Telegram Application
# -------------------------

application = Application.builder().token(BOT_TOKEN).build()

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

    status = await update.message.reply_text("⬇️ Downloading...")

    os.makedirs("downloads", exist_ok=True)

    ydl_opts = {
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
    }

    filename = None

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        await status.edit_text("📤 Uploading...")

        with open(filename, "rb") as video:
            await update.message.reply_video(video=video)

        await status.delete()

    except Exception as e:
        await status.edit_text(f"❌ Download failed.\n\n{e}")

    finally:
        if filename and os.path.exists(filename):
            os.remove(filename)


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
