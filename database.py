import sqlite3
import asyncio
import time
from typing import Optional, List, Dict, Tuple, Any
from config import DB_PATH

def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _init_db_sync():
    with _get_connection() as conn:
        cursor = conn.cursor()
        
        # Settings table (key, value)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Teams table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS teams (
                team_id TEXT PRIMARY KEY,
                user_id INTEGER NULL,
                username TEXT NULL,
                full_name TEXT NULL
            )
        """)
        
        # Stations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stations (
                station_id TEXT PRIMARY KEY,
                name TEXT NULL
            )
        """)
        
        # Routes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id TEXT,
                station_order INTEGER,
                station_id TEXT,
                FOREIGN KEY (team_id) REFERENCES teams(team_id) ON DELETE CASCADE
            )
        """)
        
        # User progress table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_progress (
                user_id INTEGER PRIMARY KEY,
                team_id TEXT,
                current_index INTEGER DEFAULT 0,
                station_start_time REAL DEFAULT 0.0,
                status TEXT DEFAULT 'in_progress'
            )
        """)
        
        conn.commit()

async def init_db():
    await asyncio.to_thread(_init_db_sync)

# Settings functions
def _get_setting_sync(key: str) -> Optional[str]:
    with _get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

def _set_setting_sync(key: str, value: str):
    with _get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

async def get_setting(key: str) -> Optional[str]:
    return await asyncio.to_thread(_get_setting_sync, key)

async def set_setting(key: str, value: str):
    await asyncio.to_thread(_set_setting_sync, key, value)


# Teams functions
def _add_team_sync(team_id: str) -> bool:
    with _get_connection() as conn:
        try:
            conn.execute("INSERT INTO teams (team_id) VALUES (?)", (team_id.strip(),))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

async def add_team(team_id: str) -> bool:
    return await asyncio.to_thread(_add_team_sync, team_id)

def _get_teams_sync() -> List[Dict[str, Any]]:
    with _get_connection() as conn:
        rows = conn.execute("SELECT * FROM teams ORDER BY team_id").fetchall()
        return [dict(row) for row in rows]

async def get_teams() -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_get_teams_sync)

def _get_team_sync(team_id: str) -> Optional[Dict[str, Any]]:
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM teams WHERE team_id = ?", (team_id.strip(),)).fetchone()
        return dict(row) if row else None

async def get_team(team_id: str) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(_get_team_sync, team_id)

def _get_team_by_user_id_sync(user_id: int) -> Optional[Dict[str, Any]]:
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM teams WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

async def get_team_by_user_id(user_id: int) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(_get_team_by_user_id_sync, user_id)

def _occupy_team_sync(team_id: str, user_id: int, username: Optional[str], full_name: Optional[str]) -> str:
    """
    Returns status string: 'SUCCESS', 'ALREADY_TAKEN', 'NOT_FOUND', 'USER_ALREADY_IN_TEAM'
    """
    with _get_connection() as conn:
        # Check if user already has a team
        existing_user_team = conn.execute("SELECT team_id FROM teams WHERE user_id = ?", (user_id,)).fetchone()
        if existing_user_team:
            if existing_user_team["team_id"] == team_id.strip():
                return "SUCCESS"
            return "USER_ALREADY_IN_TEAM"

        team = conn.execute("SELECT * FROM teams WHERE team_id = ?", (team_id.strip(),)).fetchone()
        if not team:
            return "NOT_FOUND"
        if team["user_id"] is not None and team["user_id"] != user_id:
            return "ALREADY_TAKEN"
        
        conn.execute(
            "UPDATE teams SET user_id = ?, username = ?, full_name = ? WHERE team_id = ?",
            (user_id, username, full_name, team_id.strip())
        )
        conn.commit()
        return "SUCCESS"

async def occupy_team(team_id: str, user_id: int, username: Optional[str], full_name: Optional[str]) -> str:
    return await asyncio.to_thread(_occupy_team_sync, team_id, user_id, username, full_name)

def _clear_team_sync(team_id: str) -> bool:
    with _get_connection() as conn:
        team = conn.execute("SELECT user_id FROM teams WHERE team_id = ?", (team_id.strip(),)).fetchone()
        if not team:
            return False
        user_id = team["user_id"]
        conn.execute("UPDATE teams SET user_id = NULL, username = NULL, full_name = NULL WHERE team_id = ?", (team_id.strip(),))
        if user_id:
            conn.execute("DELETE FROM user_progress WHERE user_id = ?", (user_id,))
        conn.commit()
        return True

async def clear_team(team_id: str) -> bool:
    return await asyncio.to_thread(_clear_team_sync, team_id)


# Stations functions
def _add_station_sync(station_id: str, name: Optional[str] = None) -> bool:
    with _get_connection() as conn:
        try:
            conn.execute("INSERT INTO stations (station_id, name) VALUES (?, ?)", (station_id.strip(), name))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            if name:
                conn.execute("UPDATE stations SET name = ? WHERE station_id = ?", (name, station_id.strip()))
                conn.commit()
            return True

async def add_station(station_id: str, name: Optional[str] = None) -> bool:
    return await asyncio.to_thread(_add_station_sync, station_id, name)

def _get_stations_sync() -> List[Dict[str, Any]]:
    with _get_connection() as conn:
        rows = conn.execute("SELECT * FROM stations ORDER BY station_id").fetchall()
        return [dict(row) for row in rows]

async def get_stations() -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_get_stations_sync)

def _get_station_sync(station_id: str) -> Optional[Dict[str, Any]]:
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM stations WHERE station_id = ?", (station_id.strip(),)).fetchone()
        return dict(row) if row else None

async def get_station(station_id: str) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(_get_station_sync, station_id)

def _name_station_sync(station_id: str, name: str) -> bool:
    with _get_connection() as conn:
        station = conn.execute("SELECT station_id FROM stations WHERE station_id = ?", (station_id.strip(),)).fetchone()
        if not station:
            # Auto-create if doesn't exist
            conn.execute("INSERT INTO stations (station_id, name) VALUES (?, ?)", (station_id.strip(), name.strip()))
        else:
            conn.execute("UPDATE stations SET name = ? WHERE station_id = ?", (name.strip(), station_id.strip()))
        conn.commit()
        return True

async def name_station(station_id: str, name: str) -> bool:
    return await asyncio.to_thread(_name_station_sync, station_id, name)

def _clear_station_sync(station_id: str) -> bool:
    with _get_connection() as conn:
        station = conn.execute("SELECT station_id FROM stations WHERE station_id = ?", (station_id.strip(),)).fetchone()
        if not station:
            return False
        conn.execute("DELETE FROM stations WHERE station_id = ?", (station_id.strip(),))
        conn.execute("DELETE FROM routes WHERE station_id = ?", (station_id.strip(),))
        conn.commit()
        return True

async def clear_station(station_id: str) -> bool:
    return await asyncio.to_thread(_clear_station_sync, station_id)


# Routes functions
def _set_route_sync(team_id: str, station_ids: List[str]) -> bool:
    with _get_connection() as conn:
        # Verify team exists
        team = conn.execute("SELECT team_id FROM teams WHERE team_id = ?", (team_id.strip(),)).fetchone()
        if not team:
            return False
        
        # Clear existing route
        conn.execute("DELETE FROM routes WHERE team_id = ?", (team_id.strip(),))
        
        # Insert new order
        for idx, st_id in enumerate(station_ids):
            st_clean = st_id.strip()
            # Ensure station exists in stations table
            conn.execute("INSERT OR IGNORE INTO stations (station_id) VALUES (?)", (st_clean,))
            conn.execute(
                "INSERT INTO routes (team_id, station_order, station_id) VALUES (?, ?, ?)",
                (team_id.strip(), idx, st_clean)
            )
        conn.commit()
        return True

async def set_route(team_id: str, station_ids: List[str]) -> bool:
    return await asyncio.to_thread(_set_route_sync, team_id, station_ids)

def _get_route_sync(team_id: str) -> List[Dict[str, Any]]:
    with _get_connection() as conn:
        query = """
            SELECT r.station_order, r.station_id, s.name as station_name
            FROM routes r
            LEFT JOIN stations s ON r.station_id = s.station_id
            WHERE r.team_id = ?
            ORDER BY r.station_order ASC
        """
        rows = conn.execute(query, (team_id.strip(),)).fetchall()
        return [dict(row) for row in rows]

async def get_route(team_id: str) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_get_route_sync, team_id)


# User progress functions
def _get_user_progress_sync(user_id: int) -> Optional[Dict[str, Any]]:
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM user_progress WHERE user_id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

async def get_user_progress(user_id: int) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(_get_user_progress_sync, user_id)

def _init_user_progress_sync(user_id: int, team_id: str, start_time: float) -> Dict[str, Any]:
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO user_progress (user_id, team_id, current_index, station_start_time, status)
            VALUES (?, ?, 0, ?, 'in_progress')
            """,
            (user_id, team_id.strip(), start_time)
        )
        conn.commit()
        return {
            "user_id": user_id,
            "team_id": team_id.strip(),
            "current_index": 0,
            "station_start_time": start_time,
            "status": "in_progress"
        }

async def init_user_progress(user_id: int, team_id: str, start_time: float) -> Dict[str, Any]:
    return await asyncio.to_thread(_init_user_progress_sync, user_id, team_id, start_time)

def _advance_user_station_sync(user_id: int, next_index: int, now_time: float):
    with _get_connection() as conn:
        conn.execute(
            "UPDATE user_progress SET current_index = ?, station_start_time = ? WHERE user_id = ?",
            (next_index, now_time, user_id)
        )
        conn.commit()

async def advance_user_station(user_id: int, next_index: int, now_time: float):
    await asyncio.to_thread(_advance_user_station_sync, user_id, next_index, now_time)

def _set_user_status_sync(user_id: int, status: str):
    with _get_connection() as conn:
        conn.execute("UPDATE user_progress SET status = ? WHERE user_id = ?", (status, user_id))
        conn.commit()

async def set_user_status(user_id: int, status: str):
    await asyncio.to_thread(_set_user_status_sync, user_id, status)
