import re
import time
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from config import ADMIN_GROUP_ID
import database as db

router = Router()

def is_admin_chat(message: types.Message) -> bool:
    """Check if command is coming from the configured admin group or an admin."""
    return message.chat.id == ADMIN_GROUP_ID

@router.message(Command("add_team"))
async def cmd_add_team(message: types.Message):
    if not is_admin_chat(message):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("⚠️ Використання: `/add_team (Номер)`\nНаприклад: `/add_team 1`", parse_mode="Markdown")
        return
    
    team_id = args[1].strip()
    success = await db.add_team(team_id)
    if success:
        await message.reply(f"✅ Команду **№{team_id}** успішно додано.", parse_mode="Markdown")
    else:
        await message.reply(f"⚠️ Команда **№{team_id}** вже існує в системі.", parse_mode="Markdown")


@router.message(Command("add_station"))
async def cmd_add_station(message: types.Message):
    if not is_admin_chat(message):
        return
    
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.reply("⚠️ Використання: `/add_station (Номер) [Назва]`\nНаприклад: `/add_station 1` або `/add_station 1 Парк Шевченка`", parse_mode="Markdown")
        return
    
    station_id = args[1].strip()
    name = args[2].strip() if len(args) > 2 else None
    
    await db.add_station(station_id, name)
    if name:
        await message.reply(f"✅ Станцію **№{station_id}** додано з назвою: **{name}**", parse_mode="Markdown")
    else:
        await message.reply(f"✅ Станцію **№{station_id}** додано. (Ви можете назвати її через `/name_station {station_id} Назва`)", parse_mode="Markdown")


@router.message(Command("clear_team"))
async def cmd_clear_team(message: types.Message):
    if not is_admin_chat(message):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("⚠️ Використання: `/clear_team (Номер)`\nНаприклад: `/clear_team 1`", parse_mode="Markdown")
        return
    
    team_id = args[1].strip()
    success = await db.clear_team(team_id)
    if success:
        await message.reply(f"✅ Команду **№{team_id}** звільнено від учасника та скинуто її прогрес.", parse_mode="Markdown")
    else:
        await message.reply(f"❌ Команду **№{team_id}** не знайдено.", parse_mode="Markdown")


@router.message(Command("clear_station"))
async def cmd_clear_station(message: types.Message):
    if not is_admin_chat(message):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("⚠️ Використання: `/clear_station (Номер)`\nНаприклад: `/clear_station 1`", parse_mode="Markdown")
        return
    
    station_id = args[1].strip()
    success = await db.clear_station(station_id)
    if success:
        await message.reply(f"🗑️ Станцію **№{station_id}** успішно видалено з системи та маршрутів.", parse_mode="Markdown")
    else:
        await message.reply(f"❌ Станцію **№{station_id}** не знайдено.", parse_mode="Markdown")


@router.message(Command("name_station"))
async def cmd_name_station(message: types.Message):
    if not is_admin_chat(message):
        return
    
    args = message.text.split(maxsplit=2)
    station_id = None
    name = None
    
    if len(args) >= 3:
        station_id = args[1].strip()
        name = args[2].strip()
    elif len(args) == 2 and message.reply_to_message and message.reply_to_message.text:
        station_id = args[1].strip()
        name = message.reply_to_message.text.strip()
    
    if not station_id or not name:
        await message.reply(
            "⚠️ Використання:\n"
            "1. `/name_station (Номер) (Назва)` — наприклад `/name_station 1 Парк Шевченка`\n"
            "2. Відповіддю на повідомлення з назвою: `/name_station 1`",
            parse_mode="Markdown"
        )
        return
    
    await db.name_station(station_id, name)
    await message.reply(f"✏️ Назву для станції **№{station_id}** встановлено: **{name}**", parse_mode="Markdown")


@router.message(Command("add_route"))
async def cmd_add_route(message: types.Message):
    if not is_admin_chat(message):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("⚠️ Використання: застосуйте `/add_route (Номер команди)` у відповідь на повідомлення зі списком станцій.", parse_mode="Markdown")
        return
    
    team_id = args[1].strip()
    
    if not message.reply_to_message or not message.reply_to_message.text:
        await message.reply("❌ Будь ласка, використайте команду `/add_route` у **відповідь (reply)** на повідомлення зі списком маршруту станцій!", parse_mode="Markdown")
        return
    
    route_text = message.reply_to_message.text
    # Extract station numbers/names from text
    # Split by newlines, commas, or spaces
    raw_items = re.split(r'[\n,]+', route_text)
    station_ids = [item.strip() for item in raw_items if item.strip()]
    
    if not station_ids:
        await message.reply("❌ Не вдалося знайти номери станцій у повідомленні.", parse_mode="Markdown")
        return
    
    team = await db.get_team(team_id)
    if not team:
        await message.reply(f"❌ Команду **№{team_id}** не знайдено в системі. Спочатку додайте її через `/add_team {team_id}`.", parse_mode="Markdown")
        return
    
    success = await db.set_route(team_id, station_ids)
    if success:
        formatted_list = " ➔ ".join([f"Станція №{sid}" for sid in station_ids])
        await message.reply(f"📍 Маршрут для команди **№{team_id}** успішно збережено!\nПослідовність: {formatted_list}", parse_mode="Markdown")
    else:
        await message.reply(f"❌ Помилка збереження маршруту для команди **№{team_id}**.", parse_mode="Markdown")


@router.message(Command("final_word"))
async def cmd_final_word(message: types.Message):
    if not is_admin_chat(message):
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        current_word = await db.get_setting("final_word")
        word_info = f"Поточне слово: **{current_word}**" if current_word else "Поточне слово не встановлено."
        await message.reply(f"⚠️ Використання: `/final_word (Слово)`\n{word_info}", parse_mode="Markdown")
        return
    
    word = args[1].strip()
    await db.set_setting("final_word", word)
    await message.reply(f"🔑 Фінальне ключове слово успішно встановлено: **{word}**", parse_mode="Markdown")


@router.message(Command("game_start"))
async def cmd_game_start(message: types.Message):
    if not is_admin_chat(message):
        return
    
    await db.set_setting("game_started", "1")
    
    teams = await db.get_teams()
    occupied_teams = [t for t in teams if t["user_id"] is not None]
    
    if not occupied_teams:
        await message.reply("🚀 Гра розпочата! (Зараз жоден учасник ще не зайняв номер команди. Вони отримають першу станцію одразу після авторизації).", parse_mode="Markdown")
        return
    
    started_count = 0
    now_time = time.time()
    
    done_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Виконано")]],
        resize_keyboard=True
    )
    
    for team in occupied_teams:
        user_id = team["user_id"]
        team_id = team["team_id"]
        
        route = await db.get_route(team_id)
        if not route:
            continue
        
        # Initialize progress
        await db.init_user_progress(user_id, team_id, now_time)
        
        first_station = route[0]
        st_info = await db.get_station(first_station["station_id"])
        st_name = (st_info["name"] if st_info and st_info["name"] else f"Станція №{first_station['station_id']}")
        
        msg_text = (
            f"🚀 **ГРА РОЗПОЧАЛАСЯ!**\n\n"
            f"📍 Ваша перша станція (№{first_station['station_id']}): **{st_name}**\n\n"
            f"⏱️ На виконання станції відводиться не менше 5 хвилин.\n"
            f"Після завершення натисніть кнопку **«Виконано»** нижче."
        )
        
        try:
            await message.bot.send_message(user_id, msg_text, parse_mode="Markdown", reply_markup=done_keyboard)
            started_count += 1
        except Exception as e:
            print(f"Failed to send start message to user {user_id}: {e}")
    
    await message.reply(f"🚀 **ГРА ОФІЦІЙНО РОЗПОЧАТА!**\n\nСтартову станцію та кнопку «Виконано» надіслано для **{started_count}** команд.", parse_mode="Markdown")


@router.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_admin_chat(message):
        return
    
    game_started = await db.get_setting("game_started") == "1"
    final_word = await db.get_setting("final_word") or "Не встановлено"
    teams = await db.get_teams()
    stations = await db.get_stations()
    
    status_text = (
        f"📊 **СТАТУС КВЕСТУ:**\n"
        f"• Статус гри: {'🟢 Запущено (`game_start`) ' if game_started else '🔴 Очікування запуску'}\n"
        f"• Фінальне слово: **{final_word}**\n"
        f"• Всього команд: **{len(teams)}**\n"
        f"• Всього станцій: **{len(stations)}**\n\n"
        f"📋 **Список команд:**\n"
    )
    
    if not teams:
        status_text += "_Команди ще не додані_\n"
    else:
        for t in teams:
            user_str = f"Зайнята (@{t['username'] or t['user_id']})" if t['user_id'] else "🟢 Вільна"
            route = await db.get_route(t['team_id'])
            route_str = " -> ".join([r['station_id'] for r in route]) if route else "Немає маршруту"
            status_text += f"• Команда **№{t['team_id']}**: {user_str} | Маршрут: `{route_str}`\n"
    
    await message.reply(status_text, parse_mode="Markdown")
