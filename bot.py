import os
import threading

from flask import Flask
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not found!")

application = Application.builder().token(BOT_TOKEN).build()

# --------------------------
# Flask app (for Render)
# --------------------------

app = Flask(__name__)


@app.route("/")
def home():
    return "🤖 Telegram Bot is running!"


# --------------------------
# Telegram Commands
# --------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello!\n\n"
        "Send me an Instagram Reel link."
    )


async def instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if "instagram.com" not in text:
        return

    await update.message.reply_text(
        "🚧 Downloader coming next..."
    )


application.add_handler(CommandHandler("start", start))
application.add_handler(
    MessageHandler(filters.TEXT & ~filters.COMMAND, instagram)
)


# --------------------------
# Run Telegram
# --------------------------

def run_bot():
    print("🤖 Telegram Bot Started")
    application.run_polling(
        stop_signals=None,
        close_loop=False,
    )


# --------------------------
# Main
# --------------------------

if __name__ == "__main__":

    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    port = int(os.environ.get("PORT", 10000))

    print(f"🌍 Flask running on port {port}")

    app.run(
        host="0.0.0.0",
        port=port,
    )
