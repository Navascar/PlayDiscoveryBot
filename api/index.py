import asyncio
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update

from config import BOT_TOKEN
import database as db
import admin_handlers
import user_handlers

app = Flask(__name__)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()
dp.include_router(admin_handlers.router)
dp.include_router(user_handlers.router)

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
def webhook():
    if request.method == "POST":
        try:
            update_dict = request.get_json(force=True)
            if update_dict:
                asyncio.run(handle_update(update_dict))
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    
    return "Telegram Quest Guide Bot is running via Vercel Webhook!", 200

# Vercel entrypoint handler
handler = app
