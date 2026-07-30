import asyncio
import logging
import os
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

# Register routers
dp = Dispatcher()
dp.include_router(admin_handlers.router)
dp.include_router(user_handlers.router)

# Safe lazy Bot initialization
def get_bot() -> Bot:
    if not BOT_TOKEN or "YOUR_BOT_TOKEN" in BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not configured! Please set BOT_TOKEN in Vercel Environment Variables.")
    return Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
    )

# --- Top-level WSGI / Vercel Serverless Webhook export ---
app = Flask(__name__)
handler = app  # Top-level export for Vercel

_db_initialized = False

async def handle_update(update_dict):
    global _db_initialized
    bot = get_bot()
    
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
            logger.error(f"Webhook error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    
    # GET request status page
    token_valid = bool(BOT_TOKEN and "YOUR_BOT_TOKEN" not in BOT_TOKEN)
    if not token_valid:
        return (
            "<h2>⚠️ Telegram Quest Guide Bot</h2>"
            "<p>Будь ласка, вкажіть змінні оточення <b>BOT_TOKEN</b> та <b>ADMIN_GROUP_ID</b> у налаштуваннях Vercel (Settings -> Environment Variables).</p>",
            200
        )
    return "<h2>✅ Telegram Quest Guide Bot is active!</h2>", 200


# --- Local Long Polling Entrypoint ---
async def main():
    logger.info("Initializing database...")
    await db.init_db()
    
    bot = get_bot()
    logger.info("Starting Quest Guide Bot long polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
