import traceback
import sys
from flask import Flask, request, jsonify

app = Flask(__name__)

init_error = None

try:
    import asyncio
    import logging
    import requests
    from aiogram import Bot, Dispatcher
    from aiogram.enums import ParseMode
    from aiogram.client.default import DefaultBotProperties
    from aiogram.types import Update

    from config import BOT_TOKEN
    import database as db
    import admin_handlers
    import user_handlers

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    dp = Dispatcher()
    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)

    def get_bot() -> Bot:
        if not BOT_TOKEN or "YOUR_BOT_TOKEN" in BOT_TOKEN:
            raise ValueError("BOT_TOKEN is not configured in Vercel Environment Variables.")
        return Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
        )

    _db_initialized = False

    async def process_telegram_update(update_dict):
        global _db_initialized
        bot = get_bot()
        if not _db_initialized:
            await db.init_db()
            _db_initialized = True
        
        update = Update.model_validate(update_dict, context={"bot": bot})
        await dp.feed_update(bot, update)

except Exception as err:
    init_error = f"{type(err).__name__}: {str(err)}\n\n{traceback.format_exc()}"

@app.route("/", methods=["GET", "POST"])
@app.route("/api/index", methods=["GET", "POST"])
def main_handler():
    if init_error:
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Vercel Initialization Error</title></head>
        <body style="font-family: monospace; padding: 20px;">
            <h2 style="color: red;">❌ Initialization Error on Vercel</h2>
            <pre style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; overflow-x: auto;">{init_error}</pre>
        </body>
        </html>
        """, 200

    if request.method == "POST":
        try:
            update_dict = request.get_json(force=True)
            if update_dict:
                asyncio.run(process_telegram_update(update_dict))
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            return jsonify({"status": "error", "message": str(e), "trace": traceback.format_exc()}), 500
    
    # GET Request: Webhook status page
    host_url = request.host_url.rstrip("/")
    webhook_target = f"{host_url}/api/index"
    
    token_valid = bool(BOT_TOKEN and "YOUR_BOT_TOKEN" not in BOT_TOKEN)
    
    if not token_valid:
        return (
            "<h2>⚠️ Telegram Quest Guide Bot</h2>"
            "<p>Будь ласка, додайте <b>BOT_TOKEN</b> та <b>ADMIN_GROUP_ID</b> у Vercel Settings -> Environment Variables!</p>",
            200
        )
    
    if "set_webhook" in request.args:
        try:
            tg_res = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_target}").json()
            return jsonify(tg_res)
        except Exception as err:
            return jsonify({"error": str(err)}), 500
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Telegram Quest Bot - Vercel</title></head>
    <body style="font-family: sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; border: 1px solid #eaeaea; border-radius: 10px;">
        <h2>✅ Telegram Quest Guide Bot is Active on Vercel!</h2>
        <p>Ваш Webhook URL: <code>{webhook_target}</code></p>
        <p style="margin-top: 25px;">
            <a href="/?set_webhook=1" style="background:#0070f3; color:white; padding:12px 20px; text-decoration:none; border-radius:6px; font-weight:bold;">
                👉 Натисніть тут для активації Webhook
            </a>
        </p>
    </body>
    </html>
    """, 200

handler = app
