import time
from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from config import ADMIN_GROUP_ID, STATION_COOLDOWN_SECONDS
import database as db

router = Router()

def get_done_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Виконано")]],
        resize_keyboard=True
    )

@router.message(F.chat.type == "private", CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    # Check if command has arguments like /start 1
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        team_id = args[1].strip()
        await process_team_registration(message, team_id)
        return
    
    # Check if user already registered for a team
    existing_team = await db.get_team_by_user_id(user_id)
    if existing_team:
        team_id = existing_team["team_id"]
        progress = await db.get_user_progress(user_id)
        game_started = await db.get_setting("game_started") == "1"
        
        if not game_started:
            await message.reply(
                f"👋 Ви вже зареєстровані за командою **№{team_id}**.\n"
                f"Очікуйте на початок гри від організаторів.",
                parse_mode="Markdown"
            )
            return
        
        if progress:
            if progress["status"] == "waiting_final_word":
                await message.reply("🎉 Ви пройшли всі завдання!\n\nВведіть фінальне повідомлення:", reply_markup=ReplyKeyboardRemove())
                return
            elif progress["status"] == "completed":
                await message.reply("🏆 Ви успішно завершили квест! Дякуємо за участь!", reply_markup=ReplyKeyboardRemove())
                return
            else:
                # Send current station/task
                route = await db.get_route(team_id)
                curr_idx = progress["current_index"]
                if route and curr_idx < len(route):
                    st_id = route[curr_idx]["station_id"]
                    st_info = await db.get_station(st_id)
                    st_name = st_info["name"] if st_info and st_info["name"] else st_id
                    
                    await message.reply(
                        f"📍 Ваше поточне завдання: **{st_name}**\n\n"
                        f"Після виконання натисніть кнопку **«Виконано»**.",
                        parse_mode="Markdown",
                        reply_markup=get_done_keyboard()
                    )
                    return
        
        await message.reply(f"👋 Ви зареєстровані за командою **№{team_id}**. Очікуйте нових інструкцій.", parse_mode="Markdown")
        return
    
    # Prompt to enter team number
    await message.reply(
        "👋 **Вітаємо у боті-путівнику квесту!**\n\n"
        "Будь ласка, введіть номер вашої команди (наприклад: `1`):",
        parse_mode="Markdown"
    )


async def process_team_registration(message: types.Message, team_id: str):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    result = await db.occupy_team(team_id, user_id, username, full_name)
    
    if result == "SUCCESS":
        game_started = await db.get_setting("game_started") == "1"
        
        if game_started:
            # Start player progress immediately
            now_time = time.time()
            await db.init_user_progress(user_id, team_id, now_time)
            route = await db.get_route(team_id)
            
            if route:
                first_st = route[0]["station_id"]
                st_info = await db.get_station(first_st)
                st_name = st_info["name"] if st_info and st_info["name"] else first_st
                
                await message.reply(
                    f"✅ Вашу команду **№{team_id}** підтверджено!\n🚀 **Гра вже триває!**\n\n"
                    f"📍 Ваше перше завдання: **{st_name}**\n\n"
                    f"⏱️ На виконання відводиться 5 хвилин.\n"
                    f"Після завершення натисніть кнопку **«Виконано»** нижче.",
                    parse_mode="Markdown",
                    reply_markup=get_done_keyboard()
                )
            else:
                await message.reply(
                    f"✅ Вашу команду **№{team_id}** підтверджено! Маршрут для вашої команди ще формується організаторами.",
                    parse_mode="Markdown"
                )
        else:
            await message.reply(
                f"✅ Вашу команду **№{team_id}** успішно підтверджено!\n"
                f"Очікуйте на початок гри від організаторів.",
                parse_mode="Markdown"
            )
            
    elif result == "ALREADY_TAKEN":
        await message.reply(f"❌ Номер команди **№{team_id}** вже зайнятий іншим учасником! Будь ласка, введіть інший номер команди.", parse_mode="Markdown")
    elif result == "NOT_FOUND":
        await message.reply(f"❌ Команди з номером **№{team_id}** не існує. Запитайте дійсний номер команди у організаторів.", parse_mode="Markdown")
    elif result == "USER_ALREADY_IN_TEAM":
        existing = await db.get_team_by_user_id(user_id)
        team_num = existing["team_id"] if existing else "?"
        await message.reply(f"⚠️ Ви вже зареєстровані за командою **№{team_num}**.", parse_mode="Markdown")


@router.message(F.chat.type == "private", F.text == "Виконано")
async def handle_done_button(message: types.Message):
    user_id = message.from_user.id
    progress = await db.get_user_progress(user_id)
    
    if not progress:
        await message.reply("⚠️ Ви не зареєстровані у грі або гра ще не розпочалася. Надішліть номер своєї команди.", parse_mode="Markdown")
        return
    
    if progress["status"] == "waiting_final_word":
        await message.reply("🎉 Ви вже пройшли всі завдання!\n\nВведіть фінальне повідомлення:", reply_markup=ReplyKeyboardRemove())
        return
    elif progress["status"] == "completed":
        await message.reply("🏆 Ви вже успішно завершили квест!", reply_markup=ReplyKeyboardRemove())
        return
    
    now_time = time.time()
    start_time = progress["station_start_time"]
    elapsed = now_time - start_time
    cooldown = STATION_COOLDOWN_SECONDS
    
    if elapsed < cooldown:
        remaining = int(cooldown - elapsed)
        mins = remaining // 60
        secs = remaining % 60
        
        await message.reply(
            f"⏳ Не минуло 5 хвилин, які відводяться на виконання.\n"
            f"Залишилось: **{mins} хв. {secs} сек.**",
            parse_mode="Markdown"
        )
        return
    
    # 5 minutes passed -> Advance to next station
    team_id = progress["team_id"]
    route = await db.get_route(team_id)
    
    if not route:
        await message.reply("⚠️ У вашої команди відсутній маршрут. Зверніться до адмінів.", parse_mode="Markdown")
        return
    
    curr_index = progress["current_index"]
    next_index = curr_index + 1
    
    if next_index < len(route):
        # Move to next station
        await db.advance_user_station(user_id, next_index, now_time)
        
        next_st_id = route[next_index]["station_id"]
        st_info = await db.get_station(next_st_id)
        st_name = st_info["name"] if st_info and st_info["name"] else next_st_id
        
        await message.reply(
            f"✅ Виконано!\n\n"
            f"📍 Наступне завдання: **{st_name}**\n\n"
            f"⏱️ У вас є 5 хвилин на виконання.",
            parse_mode="Markdown",
            reply_markup=get_done_keyboard()
        )
    else:
        # Reached the end of all stations!
        await db.set_user_status(user_id, "waiting_final_word")
        await message.reply(
            "🎉 **Вітаємо! Ви пройшли всі завдання.**\n\n"
            "Введіть фінальне повідомлення:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )


@router.message(F.chat.type == "private")
async def handle_private_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    progress = await db.get_user_progress(user_id)
    
    # If waiting for final word
    if progress and progress["status"] == "waiting_final_word":
        final_word = await db.get_setting("final_word")
        
        if not final_word:
            await message.reply("⚠️ Організатори ще не встановили фінальне слово. Зачекайте, будь ласка.")
            return
        
        if text.casefold() == final_word.strip().casefold():
            await db.set_user_status(user_id, "completed")
            await message.reply(
                "🏆 **Вітаємо! Ключове слово вірне.**\n"
                "Ви успішно пройшли всі завдання та завершили квест! 🥳",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            
            # Send notification to Admin group
            team_id = progress["team_id"]
            user_mention = message.from_user.mention_html(message.from_user.full_name)
            admin_msg = (
                f"🎉 **Команда №{team_id}** (Учасник: {user_mention}) успішно пройшла всі завдання "
                f"та правильно ввела фінальне слово: <b>{final_word}</b>! 🏆"
            )
            try:
                await message.bot.send_message(ADMIN_GROUP_ID, admin_msg, parse_mode="HTML")
            except Exception as e:
                print(f"Failed to notify admin group: {e}")
        else:
            await message.reply("❌ Невірне ключове слово. Спробуйте ще раз:")
        return

    # Check if participant is attempting team registration
    existing_team = await db.get_team_by_user_id(user_id)
    if not existing_team:
        # Treat text as team number input
        await process_team_registration(message, text)
    else:
        # User is already registered and typed something else
        if progress and progress["status"] == "in_progress":
            await message.reply(
                "Для підтвердження проходження натисніть кнопку **«Виконано»** під полем вводу.",
                parse_mode="Markdown",
                reply_markup=get_done_keyboard()
            )
        elif progress and progress["status"] == "completed":
            await message.reply("🏆 Ви вже успішно завершили квест!")
        else:
            await message.reply(f"Ви зареєстровані за командою **№{existing_team['team_id']}**. Очікуйте на початок гри.", parse_mode="Markdown")
