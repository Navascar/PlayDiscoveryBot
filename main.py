import asyncio
import logging
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update

from config import BOT_TOKEN
import database as db
import admin_handlers
import user_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Bot & Dispatcher
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()
dp.include_router(admin_handlers.router)
dp.include_router(user_handlers.router)

# --- Top-level WSGI / Vercel Serverless Webhook export ---
app = Flask(__name__)
handler = app  # Top-level export for Vercel

_db_initialized = False

async def handle_update(update_dict):
    global _db_initialized
    if not _db_initialized:
        await db.init_db()
        _db_initialized = True
    
    update = Update.model_validate(update_dict, context={"bot": bot})
    await dp.feed_update(bot, update)

@app.route("/", methods=["GET", "POST"])
@app.route("/api/index", methods=["GET", "POST"])
@app.route("/main", methods=["GET", "POST"])
def webhook_handler():
    if request.method == "POST":
        try:
            update_dict = request.get_json(force=True)
            if update_dict:
                asyncio.run(handle_update(update_dict))
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return "Telegram Quest Guide Bot is active!", 200


# --- Local Long Polling Entrypoint ---
async def main():
    logger.info("Initializing database...")
    await db.init_db()
    
    logger.info("Starting Quest Guide Bot long polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
