import os
import yt_dlp

from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)


# -----------------------------
# /start command
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello!\n\n"
        "Send me any public Instagram Reel or Post link and I'll download it for you."
    )


# -----------------------------
# Instagram downloader
# -----------------------------
async def instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not update.message or not update.message.text:
        return

    url = update.message.text.strip()

    if "instagram.com" not in url:
        return

    status = await update.message.reply_text("⬇️ Downloading...")

    ydl_opts = {
        "outtmpl": f"{DOWNLOAD_FOLDER}/%(id)s.%(ext)s",
        "quiet": True,
        "noplaylist": True,
    }

    try:

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(url, download=True)

            filename = ydl.prepare_filename(info)

        await status.edit_text("📤 Uploading...")

        with open(filename, "rb") as video:
            await update.message.reply_video(video=video)

        os.remove(filename)

        await status.delete()

    except Exception as e:
        await status.edit_text(f"❌ Error:\n{e}")


# -----------------------------
# Main
# -----------------------------
def main():

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            instagram,
        )
    )

    print("🤖 Bot is running...")

    app.run_polling()


if __name__ == "__main__":
    main()
