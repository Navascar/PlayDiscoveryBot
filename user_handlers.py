import time
from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from config import ADMIN_GROUP_ID, STATION_COOLDOWN_SECONDS
import database as db

router = Router()

def get_done_reply_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Виконано", style="success")]],
        resize_keyboard=True
    )

def get_done_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✅ Виконано", callback_data="done_station", style="success")]]
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
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
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
                        f"Після виконання натисніть кнопку **«✅ Виконано»**.",
                        parse_mode="Markdown",
                        reply_markup=get_done_inline_keyboard()
                    )
                    return
        
        await message.reply(f"👋 Ви зареєстровані за командою **№{team_id}**. Очікуйте нових інструкцій.", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return
    
    # Prompt to enter team number
    await message.reply(
        "👋 **Вітаємо у боті-путівнику квесту!**\n\n"
        "Будь ласка, введіть номер вашої команди (наприклад: `1`):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
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
                
                route_items = []
                for item in route:
                    st = await db.get_station(item["station_id"])
                    sname = st["name"] if st and st.get("name") else item["station_id"]
                    route_items.append(sname)
                formatted_route = " ➔ ".join(route_items)
                
                await message.reply(
                    f"✅ Вашу команду **№{team_id}** підтверджено!\n🚀 **Гра вже триває!**\n\n"
                    f"📍 **Ваш маршрут:** {formatted_route}\n\n"
                    f"🎯 Ваше перше завдання: **{st_name}**\n\n"
                    f"⏱️ На виконання відводиться 5 хвилин.\n"
                    f"Після завершення натисніть кнопку **«✅ Виконано»** нижче.",
                    parse_mode="Markdown",
                    reply_markup=get_done_inline_keyboard()
                )
            else:
                await message.reply(
                    f"✅ Вашу команду **№{team_id}** підтверджено! Маршрут для вашої команди ще формується організаторами.",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
        else:
            await message.reply(
                f"✅ Вашу команду **№{team_id}** успішно підтверджено!\n"
                f"Очікуйте на початок гри від організаторів.",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            
    elif result == "ALREADY_TAKEN":
        await message.reply(f"❌ Номер команди **№{team_id}** вже зайнятий іншим учасником! Будь ласка, введіть інший номер команди.", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    elif result == "NOT_FOUND":
        await message.reply(f"❌ Команди з номером **№{team_id}** не існує. Запитайте дійсний номер команди у організаторів.", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    elif result == "USER_ALREADY_IN_TEAM":
        existing = await db.get_team_by_user_id(user_id)
        team_num = existing["team_id"] if existing else "?"
        await message.reply(f"⚠️ Ви вже зареєстровані за командою **№{team_num}**.", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())


async def check_and_advance_station(bot, user_id: int, reply_func, alert_func=None):
    progress = await db.get_user_progress(user_id)
    
    if not progress:
        await reply_func("⚠️ Ви не зареєстровані у грі або гра ще не розпочалася. Надішліть номер своєї команди.")
        return
    
    if progress["status"] == "waiting_final_word":
        await reply_func("🎉 Ви вже пройшли всі завдання!\n\nВведіть фінальне повідомлення:")
        return
    elif progress["status"] == "completed":
        await reply_func("🏆 Ви вже успішно завершили квест!")
        return
    
    now_time = time.time()
    start_time = progress["station_start_time"]
    elapsed = now_time - start_time
    cooldown = STATION_COOLDOWN_SECONDS
    
    if elapsed < cooldown:
        remaining = int(cooldown - elapsed)
        mins = remaining // 60
        secs = remaining % 60
        warning_msg = f"⏳ Не минуло 5 хвилин, які відводяться на виконання.\nЗалишилось: {mins} хв. {secs} сек."
        
        if alert_func:
            await alert_func(warning_msg, show_alert=True)
        else:
            await reply_func(warning_msg)
        return
    
    # 5 minutes passed -> Advance to next station
    team_id = progress["team_id"]
    route = await db.get_route(team_id)
    
    if not route:
        await reply_func("⚠️ У вашої команди відсутній маршрут. Зверніться до адмінів.")
        return
    
    curr_index = progress["current_index"]
    next_index = curr_index + 1
    
    if next_index < len(route):
        await db.advance_user_station(user_id, next_index, now_time)
        
        next_st_id = route[next_index]["station_id"]
        st_info = await db.get_station(next_st_id)
        st_name = st_info["name"] if st_info and st_info["name"] else next_st_id
        
        if alert_func:
            await alert_func("✅ Завдання виконано! Наступне завдання надіслано.")
        
        await bot.send_message(
            user_id,
            f"✅ Виконано!\n\n"
            f"📍 Наступне завдання: **{st_name}**\n\n"
            f"⏱️ У вас є 5 хвилин на виконання.",
            parse_mode="Markdown",
            reply_markup=get_done_inline_keyboard()
        )
    else:
        await db.set_user_status(user_id, "waiting_final_word")
        if alert_func:
            await alert_func("🎉 Вітаємо! Ви пройшли всі завдання.")
        
        await bot.send_message(
            user_id,
            "🎉 **Вітаємо! Ви пройшли всі завдання.**\n\n"
            "Введіть фінальне повідомлення:",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )


@router.callback_query(F.data == "done_station")
async def callback_done_station(callback: types.CallbackQuery):
    await check_and_advance_station(
        bot=callback.bot,
        user_id=callback.from_user.id,
        reply_func=lambda text: callback.message.reply(text, parse_mode="Markdown"),
        alert_func=callback.answer
    )


@router.message(F.chat.type == "private", Command("skip"))
async def cmd_skip_station(message: types.Message):
    user_id = message.from_user.id
    
    # Check if admin
    try:
        member = await message.bot.get_chat_member(ADMIN_GROUP_ID, user_id)
        is_admin = member.status in ("creator", "administrator", "member")
    except Exception:
        is_admin = True
    
    if not is_admin:
        return
    
    args = message.text.split(maxsplit=1)
    target = args[1].strip() if len(args) > 1 else user_id
    
    res = await db.force_skip_user_station(target)
    if not res:
        await message.reply("⚠️ Не вдалося пропустити станцію. Перевірте, чи гра триває та чи є активне завдання.", parse_mode="Markdown")
        return
    
    target_uid = res["user_id"]
    team_id = res["team_id"]
    
    if res["status"] == "in_progress":
        st_name = res["next_station_name"]
        await message.reply(f"⏩ Станцію для команди **№{team_id}** успішно пропущено!", parse_mode="Markdown")
        try:
            await message.bot.send_message(
                target_uid,
                f"⏩ **Організатори пропустили станцію!**\n\n"
                f"📍 Наступне завдання: **{st_name}**\n\n"
                f"⏱️ У вас є 5 хвилин на виконання.",
                parse_mode="Markdown",
                reply_markup=get_done_inline_keyboard()
            )
        except Exception as e:
            print(f"Failed to notify user on skip: {e}")
    elif res["status"] == "waiting_final_word":
        await message.reply(f"⏩ Станцію для команди **№{team_id}** успішно пропущено! Команда перейшла до фінального слова.", parse_mode="Markdown")
        try:
            await message.bot.send_message(
                target_uid,
                "🎉 **Вітаємо! Всі станції пройдено.**\n\n"
                "Введіть фінальне повідомлення:",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            print(f"Failed to notify user on skip: {e}")


@router.message(F.chat.type == "private", F.text.in_({"🟢 ✅ Виконано", "✅ Виконано", "Виконано"}))
async def handle_done_button(message: types.Message):
    await check_and_advance_station(
        bot=message.bot,
        user_id=message.from_user.id,
        reply_func=lambda text: message.reply(text, parse_mode="Markdown")
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
            await message.reply("⚠️ Організатори ще не встановили фінальне слово. Зачекайте, будь ласка.", reply_markup=ReplyKeyboardRemove())
            return
        
        if text.casefold() == final_word.strip().casefold():
            completion = await db.complete_user_quest(user_id)
            place = completion.get("finish_order", 1)
            attempts = completion.get("keyword_attempts", 1)
            
            medals = {1: "🥇", 2: "🥈", 3: "🥉"}
            medal = medals.get(place, "🎖️")
            
            await message.reply(
                f"🏆 **Вітаємо! Ключове слово вірне.**\n\n"
                f"{medal} Ви посіли **{place}-е місце** у квесті!\n"
                f"📊 Кількість спроб вводу: **{attempts}**\n\n"
                f"Ви успішно пройшли всі завдання та завершили квест! 🥳",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            
            # Send notification to Admin group
            team_id = progress["team_id"]
            user_mention = message.from_user.mention_html(message.from_user.full_name)
            admin_msg = (
                f"🎉 <b>Команда №{team_id}</b> (Учасник: {user_mention}) фінішувала!<br>"
                f"🏆 <b>Місце: {place}</b> ({medal})<br>"
                f"🔑 Фінальне слово: <b>{final_word}</b><br>"
                f"📊 Кількість спроб вводу: <b>{attempts}</b>"
            ).replace("<br>", "\n")
            
            try:
                await message.bot.send_message(ADMIN_GROUP_ID, admin_msg, parse_mode="HTML")
            except Exception as e:
                print(f"Failed to notify admin group: {e}")
                
            # Check if all active registered teams have completed
            all_done = await db.check_all_teams_completed()
            if all_done:
                await db.set_setting("game_started", "0")
                leaderboard = await db.get_leaderboard()
                
                lb_text = "🏁 **КВЕСТ ОФІЦІЙНО ЗАВЕРШЕНО!**\nВсі команди пройшли свої маршрути!\n\n🏆 **ПІДСУМКОВИЙ ТУРНІРНИЙ СПИСОК:**\n"
                for item in leaderboard:
                    p = item.get("finish_order", "?")
                    tid = item.get("team_id", "?")
                    att = item.get("keyword_attempts", 1)
                    m = medals.get(p, "🎖️")
                    lb_text += f"{m} **{p}-е місце**: Команда **№{tid}** (спроб: `{att}`)\n"
                
                # Broadcast to all registered participants
                teams = await db.get_teams()
                for t in teams:
                    if t.get("user_id"):
                        try:
                            await message.bot.send_message(
                                t["user_id"],
                                lb_text,
                                parse_mode="Markdown",
                                reply_markup=ReplyKeyboardRemove()
                            )
                        except Exception:
                            pass
                
                # Notify admin group
                try:
                    await message.bot.send_message(ADMIN_GROUP_ID, lb_text, parse_mode="Markdown")
                except Exception:
                    pass
        else:
            attempts = await db.increment_keyword_attempts(user_id)
            await message.reply(
                f"❌ Невірне ключове слово (Спроба №{attempts}). Спробуйте ще раз:",
                reply_markup=ReplyKeyboardRemove()
            )
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
                "Для підтвердження проходження натисніть кнопку **«✅ Виконано»** під завданням.",
                parse_mode="Markdown",
                reply_markup=get_done_inline_keyboard()
            )
        elif progress and progress["status"] == "completed":
            await message.reply("🏆 Ви вже успішно завершили квест!", reply_markup=ReplyKeyboardRemove())
        else:
            await message.reply(f"Ви зареєстровані за командою **№{existing_team['team_id']}**. Очікуйте на початок гри.", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
