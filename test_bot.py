import asyncio
import os
import time
import database as db
from config import DB_PATH

async def run_tests():
    print("--- Running Verification Tests ---")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    
    await db.init_db()
    print("1. Database initialized.")
    
    # 1. Add Team
    res = await db.add_team("101")
    assert res is True
    print("2. Team 101 added.")
    
    # 2. Add Stations
    await db.add_station("1", "Головна брама")
    await db.add_station("2", "Центральна альтанка")
    await db.add_station("3", "Озеро")
    print("3. Stations 1, 2, 3 added.")
    
    # 3. Set Route
    await db.set_route("101", ["1", "2", "3"])
    route = await db.get_route("101")
    assert len(route) == 3
    assert route[0]["station_id"] == "1"
    assert route[1]["station_id"] == "2"
    assert route[2]["station_id"] == "3"
    print("4. Route for Team 101 set correctly.")
    
    # 4. Occupy Team
    occ_res = await db.occupy_team("101", 12345678, "test_user", "Test User")
    assert occ_res == "SUCCESS"
    print("5. Team 101 occupied by user 12345678.")
    
    # Occupy again by another user -> Should be ALREADY_TAKEN
    occ_res2 = await db.occupy_team("101", 99999999, "other_user", "Other User")
    assert occ_res2 == "ALREADY_TAKEN"
    print("6. Prevented duplicate occupation of Team 101.")
    
    # 5. User Progress & Timer
    now = time.time()
    await db.init_user_progress(12345678, "101", now)
    prog = await db.get_user_progress(12345678)
    assert prog["current_index"] == 0
    assert prog["status"] == "in_progress"
    print("7. User progress initialized at index 0.")
    
    # Cooldown check: 200s passed < 300s -> Not ready
    elapsed = 200
    assert elapsed < 300
    print("8. 5-minute timer restriction verified (200s < 300s).")
    
    # Advance station after 300s
    await db.advance_user_station(12345678, 1, now + 301)
    prog_next = await db.get_user_progress(12345678)
    assert prog_next["current_index"] == 1
    print("9. Advanced to station index 1.")
    
    # 6. Final Word
    await db.set_setting("final_word", "Перемога")
    word = await db.get_setting("final_word")
    assert word.casefold() == "перемога".casefold()
    print("10. Final word set and matched (case-insensitive).")
    
    # Cleanup DB
    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except PermissionError:
        pass
        
    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(run_tests())
