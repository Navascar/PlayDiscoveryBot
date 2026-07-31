import asyncio
import time
import os
from typing import Optional, List, Dict, Any
from config import DB_PATH

try:
    import sqlite3
    HAS_SQLITE = True
except ImportError:
    HAS_SQLITE = False
    import json

# Fallback JSON storage path if sqlite3 C-extension is not available on Vercel
JSON_DB_PATH = "/tmp/bot_data.json" if os.getenv("VERCEL") else "bot_data.json"

def _get_json_db() -> Dict[str, Any]:
    if not os.path.exists(JSON_DB_PATH):
        return {
            "settings": {},
            "teams": {},
            "stations": {},
            "routes": {},
            "user_progress": {}
        }
    try:
        with open(JSON_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "settings": {},
            "teams": {},
            "stations": {},
            "routes": {},
            "user_progress": {}
        }

def _save_json_db(data: Dict[str, Any]):
    with open(JSON_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _get_connection():
    if not HAS_SQLITE:
        raise RuntimeError("SQLite3 is not available in this Python runtime environment.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db_sync():
    if not HAS_SQLITE:
        _save_json_db(_get_json_db())
        return
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS teams (team_id TEXT PRIMARY KEY, user_id INTEGER NULL, username TEXT NULL, full_name TEXT NULL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS stations (station_id TEXT PRIMARY KEY, name TEXT NULL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS routes (id INTEGER PRIMARY KEY AUTOINCREMENT, team_id TEXT, station_order INTEGER, station_id TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS user_progress (user_id INTEGER PRIMARY KEY, team_id TEXT, current_index INTEGER DEFAULT 0, station_start_time REAL DEFAULT 0.0, status TEXT DEFAULT 'in_progress')")
        conn.commit()

async def init_db():
    await asyncio.to_thread(_init_db_sync)

# Settings functions
def _get_setting_sync(key: str) -> Optional[str]:
    if not HAS_SQLITE:
        db = _get_json_db()
        return db["settings"].get(key)
    with _get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

def _set_setting_sync(key: str, value: str):
    if not HAS_SQLITE:
        db = _get_json_db()
        db["settings"][key] = str(value)
        _save_json_db(db)
        return
    with _get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

async def get_setting(key: str) -> Optional[str]:
    return await asyncio.to_thread(_get_setting_sync, key)

async def set_setting(key: str, value: str):
    await asyncio.to_thread(_set_setting_sync, key, value)

# Teams functions
def _add_team_sync(team_id: str) -> bool:
    import re
    tids = [t.strip() for t in re.split(r'[\s,]+', team_id) if t.strip()]
    if not tids:
        return False
    if not HAS_SQLITE:
        db = _get_json_db()
        added_any = False
        for tid in tids:
            if tid not in db["teams"]:
                db["teams"][tid] = {"team_id": tid, "user_id": None, "username": None, "full_name": None}
                added_any = True
        _save_json_db(db)
        return added_any
    with _get_connection() as conn:
        added_any = False
        for tid in tids:
            try:
                conn.execute("INSERT INTO teams (team_id) VALUES (?)", (tid,))
                added_any = True
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        return added_any

async def add_team(team_id: str) -> bool:
    return await asyncio.to_thread(_add_team_sync, team_id)

def _get_teams_sync() -> List[Dict[str, Any]]:
    if not HAS_SQLITE:
        db = _get_json_db()
        return list(db["teams"].values())
    with _get_connection() as conn:
        rows = conn.execute("SELECT * FROM teams ORDER BY team_id").fetchall()
        return [dict(row) for row in rows]

async def get_teams() -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_get_teams_sync)

def _get_team_sync(team_id: str) -> Optional[Dict[str, Any]]:
    tid = team_id.strip()
    if not HAS_SQLITE:
        db = _get_json_db()
        return db["teams"].get(tid)
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM teams WHERE team_id = ?", (tid,)).fetchone()
        return dict(row) if row else None

async def get_team(team_id: str) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(_get_team_sync, team_id)

def _get_team_by_user_id_sync(user_id: int) -> Optional[Dict[str, Any]]:
    if not HAS_SQLITE:
        db = _get_json_db()
        for t in db["teams"].values():
            if t["user_id"] == user_id:
                return t
        return None
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM teams WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

async def get_team_by_user_id(user_id: int) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(_get_team_by_user_id_sync, user_id)

def _occupy_team_sync(team_id: str, user_id: int, username: Optional[str], full_name: Optional[str]) -> str:
    tid = team_id.strip()
    if not HAS_SQLITE:
        db = _get_json_db()
        for t in db["teams"].values():
            if t["user_id"] == user_id:
                return "SUCCESS" if t["team_id"] == tid else "USER_ALREADY_IN_TEAM"
        if tid not in db["teams"]:
            return "NOT_FOUND"
        team = db["teams"][tid]
        if team["user_id"] is not None and team["user_id"] != user_id:
            return "ALREADY_TAKEN"
        team["user_id"] = user_id
        team["username"] = username
        team["full_name"] = full_name
        _save_json_db(db)
        return "SUCCESS"

    with _get_connection() as conn:
        existing_user_team = conn.execute("SELECT team_id FROM teams WHERE user_id = ?", (user_id,)).fetchone()
        if existing_user_team:
            if existing_user_team["team_id"] == tid:
                return "SUCCESS"
            return "USER_ALREADY_IN_TEAM"

        team = conn.execute("SELECT * FROM teams WHERE team_id = ?", (tid,)).fetchone()
        if not team:
            return "NOT_FOUND"
        if team["user_id"] is not None and team["user_id"] != user_id:
            return "ALREADY_TAKEN"
        
        conn.execute("UPDATE teams SET user_id = ?, username = ?, full_name = ? WHERE team_id = ?", (user_id, username, full_name, tid))
        conn.commit()
        return "SUCCESS"

async def occupy_team(team_id: str, user_id: int, username: Optional[str], full_name: Optional[str]) -> str:
    return await asyncio.to_thread(_occupy_team_sync, team_id, user_id, username, full_name)

def _clear_team_sync(team_id: str) -> bool:
    tid = team_id.strip()
    if not HAS_SQLITE:
        db = _get_json_db()
        if tid not in db["teams"]:
            return False
        user_id = db["teams"][tid]["user_id"]
        db["teams"][tid]["user_id"] = None
        db["teams"][tid]["username"] = None
        db["teams"][tid]["full_name"] = None
        if user_id and str(user_id) in db["user_progress"]:
            del db["user_progress"][str(user_id)]
        _save_json_db(db)
        return True

    with _get_connection() as conn:
        team = conn.execute("SELECT user_id FROM teams WHERE team_id = ?", (tid,)).fetchone()
        if not team:
            return False
        user_id = team["user_id"]
        conn.execute("UPDATE teams SET user_id = NULL, username = NULL, full_name = NULL WHERE team_id = ?", (tid,))
        if user_id:
            conn.execute("DELETE FROM user_progress WHERE user_id = ?", (user_id,))
        conn.commit()
        return True

async def clear_team(team_id: str) -> bool:
    return await asyncio.to_thread(_clear_team_sync, team_id)

# Stations functions
def _add_station_sync(station_id: str, name: Optional[str] = None) -> bool:
    sid = station_id.strip()
    if not HAS_SQLITE:
        db = _get_json_db()
        if sid not in db["stations"]:
            db["stations"][sid] = {"station_id": sid, "name": name}
        elif name:
            db["stations"][sid]["name"] = name
        _save_json_db(db)
        return True

    with _get_connection() as conn:
        try:
            conn.execute("INSERT INTO stations (station_id, name) VALUES (?, ?)", (sid, name))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            if name:
                conn.execute("UPDATE stations SET name = ? WHERE station_id = ?", (name, sid))
                conn.commit()
            return True

async def add_station(station_id: str, name: Optional[str] = None) -> bool:
    return await asyncio.to_thread(_add_station_sync, station_id, name)

def _get_stations_sync() -> List[Dict[str, Any]]:
    if not HAS_SQLITE:
        db = _get_json_db()
        return list(db["stations"].values())
    with _get_connection() as conn:
        rows = conn.execute("SELECT * FROM stations ORDER BY station_id").fetchall()
        return [dict(row) for row in rows]

async def get_stations() -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_get_stations_sync)

def _get_station_sync(station_id: str) -> Optional[Dict[str, Any]]:
    sid = station_id.strip()
    if not HAS_SQLITE:
        db = _get_json_db()
        return db["stations"].get(sid)
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM stations WHERE station_id = ?", (sid,)).fetchone()
        return dict(row) if row else None

async def get_station(station_id: str) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(_get_station_sync, station_id)

def _name_station_sync(station_id: str, name: str) -> bool:
    sid = station_id.strip()
    nm = name.strip()
    if not HAS_SQLITE:
        db = _get_json_db()
        db["stations"][sid] = {"station_id": sid, "name": nm}
        _save_json_db(db)
        return True

    with _get_connection() as conn:
        station = conn.execute("SELECT station_id FROM stations WHERE station_id = ?", (sid,)).fetchone()
        if not station:
            conn.execute("INSERT INTO stations (station_id, name) VALUES (?, ?)", (sid, nm))
        else:
            conn.execute("UPDATE stations SET name = ? WHERE station_id = ?", (nm, sid))
        conn.commit()
        return True

async def name_station(station_id: str, name: str) -> bool:
    return await asyncio.to_thread(_name_station_sync, station_id, name)

def _clear_station_sync(station_id: str) -> bool:
    sid = station_id.strip()
    if not HAS_SQLITE:
        db = _get_json_db()
        if sid not in db["stations"]:
            return False
        del db["stations"][sid]
        for tid in db["routes"]:
            db["routes"][tid] = [s for s in db["routes"][tid] if s != sid]
        _save_json_db(db)
        return True

    with _get_connection() as conn:
        station = conn.execute("SELECT station_id FROM stations WHERE station_id = ?", (sid,)).fetchone()
        if not station:
            return False
        conn.execute("DELETE FROM stations WHERE station_id = ?", (sid,))
        conn.execute("DELETE FROM routes WHERE station_id = ?", (sid,))
        conn.commit()
        return True

async def clear_station(station_id: str) -> bool:
    return await asyncio.to_thread(_clear_station_sync, station_id)

# Routes functions
def _set_route_sync(team_id: str, station_ids: List[str]) -> bool:
    tid = team_id.strip()
    cleaned_ids = [s.strip() for s in station_ids if s.strip()]
    if not HAS_SQLITE:
        db = _get_json_db()
        if tid not in db["teams"]:
            db["teams"][tid] = {"team_id": tid, "user_id": None, "username": None, "full_name": None}
        db["routes"][tid] = cleaned_ids
        for sid in cleaned_ids:
            if sid not in db["stations"]:
                db["stations"][sid] = {"station_id": sid, "name": None}
        _save_json_db(db)
        return True

    with _get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO teams (team_id) VALUES (?)", (tid,))
        conn.execute("DELETE FROM routes WHERE team_id = ?", (tid,))
        for idx, st_id in enumerate(cleaned_ids):
            conn.execute("INSERT OR IGNORE INTO stations (station_id) VALUES (?)", (st_id,))
            conn.execute("INSERT INTO routes (team_id, station_order, station_id) VALUES (?, ?, ?)", (tid, idx, st_id))
        conn.commit()
        return True

async def set_route(team_id: str, station_ids: List[str]) -> bool:
    return await asyncio.to_thread(_set_route_sync, team_id, station_ids)

def _get_route_sync(team_id: str) -> List[Dict[str, Any]]:
    tid = team_id.strip()
    if not HAS_SQLITE:
        db = _get_json_db()
        st_ids = db["routes"].get(tid, [])
        res = []
        for idx, sid in enumerate(st_ids):
            st = db["stations"].get(sid, {})
            res.append({"station_order": idx, "station_id": sid, "station_name": st.get("name")})
        return res

    with _get_connection() as conn:
        query = """
            SELECT r.station_order, r.station_id, s.name as station_name
            FROM routes r
            LEFT JOIN stations s ON r.station_id = s.station_id
            WHERE r.team_id = ?
            ORDER BY r.station_order ASC
        """
        rows = conn.execute(query, (tid,)).fetchall()
        return [dict(row) for row in rows]

async def get_route(team_id: str) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_get_route_sync, team_id)

# User progress functions
def _get_user_progress_sync(user_id: int) -> Optional[Dict[str, Any]]:
    uid_str = str(user_id)
    if not HAS_SQLITE:
        db = _get_json_db()
        return db["user_progress"].get(uid_str)
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM user_progress WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

async def get_user_progress(user_id: int) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(_get_user_progress_sync, user_id)

def _init_user_progress_sync(user_id: int, team_id: str, start_time: float) -> Dict[str, Any]:
    tid = team_id.strip()
    uid_str = str(user_id)
    p_data = {
        "user_id": user_id,
        "team_id": tid,
        "current_index": 0,
        "station_start_time": start_time,
        "status": "in_progress"
    }
    if not HAS_SQLITE:
        db = _get_json_db()
        db["user_progress"][uid_str] = p_data
        _save_json_db(db)
        return p_data

    with _get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO user_progress (user_id, team_id, current_index, station_start_time, status) VALUES (?, ?, 0, ?, 'in_progress')",
            (user_id, tid, start_time)
        )
        conn.commit()
        return p_data

async def init_user_progress(user_id: int, team_id: str, start_time: float) -> Dict[str, Any]:
    return await asyncio.to_thread(_init_user_progress_sync, user_id, team_id, start_time)

def _advance_user_station_sync(user_id: int, next_index: int, now_time: float):
    uid_str = str(user_id)
    if not HAS_SQLITE:
        db = _get_json_db()
        if uid_str in db["user_progress"]:
            db["user_progress"][uid_str]["current_index"] = next_index
            db["user_progress"][uid_str]["station_start_time"] = now_time
            _save_json_db(db)
        return
    with _get_connection() as conn:
        conn.execute("UPDATE user_progress SET current_index = ?, station_start_time = ? WHERE user_id = ?", (next_index, now_time, user_id))
        conn.commit()

async def advance_user_station(user_id: int, next_index: int, now_time: float):
    await asyncio.to_thread(_advance_user_station_sync, user_id, next_index, now_time)

def _set_user_status_sync(user_id: int, status: str):
    uid_str = str(user_id)
    if not HAS_SQLITE:
        db = _get_json_db()
        if uid_str in db["user_progress"]:
            db["user_progress"][uid_str]["status"] = status
            _save_json_db(db)
        return
    with _get_connection() as conn:
        conn.execute("UPDATE user_progress SET status = ? WHERE user_id = ?", (status, user_id))
        conn.commit()

async def set_user_status(user_id: int, status: str):
    await asyncio.to_thread(_set_user_status_sync, user_id, status)

def _stop_game_reset_sync():
    if not HAS_SQLITE:
        db = _get_json_db()
        db["settings"]["game_started"] = "0"
        db["user_progress"] = {}
        for tid in db["teams"]:
            db["teams"][tid]["user_id"] = None
            db["teams"][tid]["username"] = None
            db["teams"][tid]["full_name"] = None
        _save_json_db(db)
        return
    with _get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('game_started', '0')")
        conn.execute("DELETE FROM user_progress")
        conn.execute("UPDATE teams SET user_id = NULL, username = NULL, full_name = NULL")
        conn.commit()

async def stop_game_reset():
    await asyncio.to_thread(_stop_game_reset_sync)

def _clear_routes_sync(team_id: Optional[str] = None) -> bool:
    if not HAS_SQLITE:
        db = _get_json_db()
        if team_id:
            tid = team_id.strip()
            if tid in db["routes"]:
                del db["routes"][tid]
        else:
            db["routes"] = {}
        _save_json_db(db)
        return True

    with _get_connection() as conn:
        if team_id:
            conn.execute("DELETE FROM routes WHERE team_id = ?", (team_id.strip(),))
        else:
            conn.execute("DELETE FROM routes")
        conn.commit()
        return True

async def clear_routes(team_id: Optional[str] = None) -> bool:
    return await asyncio.to_thread(_clear_routes_sync, team_id)


