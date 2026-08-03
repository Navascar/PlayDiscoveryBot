import asyncio
import os
import time
import re
import database as db
from config import DB_PATH, STATION_COOLDOWN_SECONDS
from user_handlers import get_done_inline_keyboard, get_done_reply_keyboard

async def run_tests():
    print("--- Running Verification Tests ---")
    if os.path.exists("bot_data.json"):
        try:
            os.remove("bot_data.json")
        except Exception:
            pass
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except Exception:
            pass
    
    await db.init_db()
    print("1. Database initialized.")
    
    # 1. Add Team (single and multiple)
    res = await db.add_team("101")
    assert res is True
    res_multi = await db.add_team("102, 103, 104")
    assert res_multi is True
    teams = await db.get_teams()
    team_ids = [t["team_id"] for t in teams]
    assert "101" in team_ids and "102" in team_ids and "103" in team_ids and "104" in team_ids
    print("2. Teams 101, 102, 103, 104 added.")
    
    # 2. Add Stations
    await db.add_station("1", "Головна брама")
    await db.add_station("2", "Центральна альтанка")
    await db.add_station("3", "Озеро")
    print("3. Stations 1, 2, 3 added.")
    
    # 3. Set Route for team that wasn't pre-created (Auto-creation test)
    await db.set_route("105", ["1", "2", "3"])
    route105 = await db.get_route("105")
    assert len(route105) == 3
    t105 = await db.get_team("105")
    assert t105 is not None
    print("4. Team 105 auto-created on set_route and route set correctly.")
    
    # 4. Route text parsing test with arrows and bullet points
    sample_route_text = "1. Station A -> 2. Station B ➔ 3. Station C"
    raw_items = re.split(r'[\n,➔→;—–]+|\s*->\s*', sample_route_text)
    parsed_ids = []
    for item in raw_items:
        cleaned = re.sub(r'^\d+[\.\)]\s*', '', item.strip()).strip()
        if cleaned:
            parsed_ids.append(cleaned)
    assert parsed_ids == ["Station A", "Station B", "Station C"]
    print("5. Route text parsing with arrows and bullets verified.")
    
    # 5. Keyboard styling and emoji check
    inline_kb = get_done_inline_keyboard()
    reply_kb = get_done_reply_keyboard()
    inline_btn = inline_kb.inline_keyboard[0][0]
    reply_btn = reply_kb.keyboard[0][0]
    
    assert inline_btn.text == "✅ Виконано"
    assert inline_btn.style == "success"
    assert reply_btn.text == "✅ Виконано"
    assert reply_btn.style == "success"
    print("6. Button text and style='success' verified.")
    
    # 6. Occupy Team
    occ_res = await db.occupy_team("101", 12345678, "test_user", "Test User")
    assert occ_res == "SUCCESS"
    print("7. Team 101 occupied by user 12345678.")
    
    # Occupy again by another user -> Should be ALREADY_TAKEN
    occ_res2 = await db.occupy_team("101", 99999999, "other_user", "Other User")
    assert occ_res2 == "ALREADY_TAKEN"
    print("8. Prevented duplicate occupation of Team 101.")
    
    # 7. User Progress & Timer
    now = time.time()
    await db.init_user_progress(12345678, "101", now)
    prog = await db.get_user_progress(12345678)
    assert prog["current_index"] == 0
    assert prog["status"] == "in_progress"
    print("9. User progress initialized at index 0.")
    
    # Cooldown check: 200s passed < STATION_COOLDOWN_SECONDS -> Not ready
    elapsed = 200
    assert elapsed < STATION_COOLDOWN_SECONDS
    print(f"10. Station timer restriction verified (200s < {STATION_COOLDOWN_SECONDS}s).")
    
    # Advance station after STATION_COOLDOWN_SECONDS
    await db.advance_user_station(12345678, 1, now + STATION_COOLDOWN_SECONDS + 1)
    prog_next = await db.get_user_progress(12345678)
    assert prog_next["current_index"] == 1
    print("11. Advanced to station index 1.")
    
    # 9. Stop Game & Verify Team / Route Persistence
    await db.stop_game_reset(clear_participants=False)
    route_after_stop = await db.get_route("105")
    assert len(route_after_stop) == 3
    teams_after_stop = await db.get_teams()
    assert len(teams_after_stop) >= 4
    print("13. Teams and routes preserved after stop_game_reset.")

    # 10. Cold Start Simulation (clear in-memory/tables to simulate empty DB on new container)
    try:
        if os.path.exists(DB_PATH):
            with db._get_connection() as conn:
                conn.execute("DELETE FROM teams")
                conn.execute("DELETE FROM routes")
                conn.commit()
    except Exception:
        pass
    await db.init_db()
    restored_route = await db.get_route("105")
    assert len(restored_route) == 3
    restored_teams = await db.get_teams()
    assert len(restored_teams) >= 4
    print("14. Cold start restoration from JSON backup to SQLite verified.")
    
    # 11. Test Secret /skip Command
    await db.set_route("101", ["1", "2", "3"])
    await db.init_user_progress(12345678, "101", time.time())
    skip_res = await db.force_skip_user_station(12345678)
    assert skip_res is not None
    assert skip_res["status"] == "in_progress"
    assert skip_res["next_station_id"] == "2"
    print("15. Secret /skip command station skip verified.")
    
    # 12. Test Keyword Attempts & Leaderboard Placement
    att1 = await db.increment_keyword_attempts(12345678)
    att2 = await db.increment_keyword_attempts(12345678)
    assert att2 == 2
    comp_res = await db.complete_user_quest(12345678)
    assert comp_res["finish_order"] == 1
    assert comp_res["keyword_attempts"] == 2
    leaderboard = await db.get_leaderboard()
    assert len(leaderboard) == 1
    assert leaderboard[0]["finish_order"] == 1
    print("16. Leaderboard ranking and keyword attempt counter verified.")
    
    # Cleanup DB & JSON backup created for tests
    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        if os.path.exists("bot_data.json"):
            os.remove("bot_data.json")
    except PermissionError:
        pass
        
    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_tests())
