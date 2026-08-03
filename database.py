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

import json

import urllib.request
import urllib.parse

# Fallback JSON storage paths (/tmp/bot_data.json takes priority over static bot_data.json)
JSON_PATHS = [
    "/tmp/bot_data.json",
    "bot_data.json"
]

def _fetch_kv_db() -> Optional[Dict[str, Any]]:
    url = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return None
    try:
        req_url = f"{url.rstrip('/')}/get/bot_data_json"
        req = urllib.request.Request(req_url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=5) as response:
            res = json.loads(response.read().decode("utf-8"))
            val = res.get("result")
            if val:
                if isinstance(val, str):
                    return json.loads(val)
                elif isinstance(val, dict):
                    return val
    except Exception:
        pass
    return None

def _save_kv_db(data: Dict[str, Any]):
    url = os.getenv("KV_REST_API_URL") or os.getenv("UPSTASH_REDIS_REST_URL")
    token = os.getenv("KV_REST_API_TOKEN") or os.getenv("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        return
    try:
        json_str = json.dumps(data, ensure_ascii=False)
        req_url = f"{url.rstrip('/')}/set/bot_data_json"
        req_data = json_str.encode("utf-8")
        req = urllib.request.Request(req_url, data=req_data, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as response:
            pass
    except Exception:
        pass

def _get_bot_and_group():
    try:
        from config import BOT_TOKEN, ADMIN_GROUP_ID
        if not BOT_TOKEN or "YOUR_BOT_TOKEN" in BOT_TOKEN or not ADMIN_GROUP_ID:
            return None, None
        return BOT_TOKEN, ADMIN_GROUP_ID
    except Exception:
        return None, None

def _fetch_telegram_backup() -> Optional[Dict[str, Any]]:
    bot_token, admin_group_id = _get_bot_and_group()
    if not bot_token or not admin_group_id:
        return None
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getChat?chat_id={admin_group_id}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if not res.get("ok"):
                return None
            chat = res.get("result", {})
            pinned = chat.get("pinned_message")
            if not pinned:
                return None
            
            text = pinned.get("text") or pinned.get("caption") or ""
            if "[BOT_DB_BACKUP]" not in text:
                return None
            
            if "```json" in text:
                json_part = text.split("```json")[1].split("```")[0].strip()
                return json.loads(json_part)
            elif text.strip().startswith("{") and text.strip().endswith("}"):
                return json.loads(text.strip())
            
            doc = pinned.get("document")
            if doc and doc.get("file_id"):
                file_id = doc["file_id"]
                file_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
                with urllib.request.urlopen(urllib.request.Request(file_url), timeout=5) as f_resp:
                    f_res = json.loads(f_resp.read().decode("utf-8"))
                    file_path = f_res.get("result", {}).get("file_path")
                    if file_path:
                        dl_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
                        with urllib.request.urlopen(urllib.request.Request(dl_url), timeout=5) as dl_resp:
                            content = dl_resp.read().decode("utf-8")
                            return json.loads(content)
    except Exception:
        pass
    return None

_telegram_backup_msg_id = None

def _save_telegram_backup(data: Dict[str, Any]):
    global _telegram_backup_msg_id
    bot_token, admin_group_id = _get_bot_and_group()
    if not bot_token or not admin_group_id:
        return

    # Safety check: do not overwrite a non-empty backup with an empty database
    has_content = bool(data.get("teams") or data.get("routes") or data.get("stations"))
    if not has_content:
        existing = _fetch_telegram_backup()
        if existing and (existing.get("teams") or existing.get("routes")):
            return

    try:
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        
        if not _telegram_backup_msg_id:
            try:
                get_chat_url = f"https://api.telegram.org/bot{bot_token}/getChat?chat_id={admin_group_id}"
                with urllib.request.urlopen(urllib.request.Request(get_chat_url), timeout=4) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    if res.get("ok"):
                        pinned = res.get("result", {}).get("pinned_message")
                        if pinned:
                            p_text = pinned.get("text") or pinned.get("caption") or ""
                            if "[BOT_DB_BACKUP]" in p_text:
                                _telegram_backup_msg_id = pinned.get("message_id")
            except Exception:
                pass

        if len(json_str) < 3800:
            msg_text = f"🤖 [BOT_DB_BACKUP]\n```json\n{json_str}\n```"
            if _telegram_backup_msg_id:
                edit_url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
                payload = json.dumps({
                    "chat_id": admin_group_id,
                    "message_id": _telegram_backup_msg_id,
                    "text": msg_text,
                    "parse_mode": "Markdown"
                }).encode("utf-8")
                req = urllib.request.Request(edit_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                try:
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        res = json.loads(resp.read().decode("utf-8"))
                        if res.get("ok"):
                            return
                except Exception:
                    pass
            
            send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = json.dumps({
                "chat_id": admin_group_id,
                "text": msg_text,
                "parse_mode": "Markdown"
            }).encode("utf-8")
            req = urllib.request.Request(send_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("ok"):
                    msg_id = res["result"]["message_id"]
                    _telegram_backup_msg_id = msg_id
                    pin_url = f"https://api.telegram.org/bot{bot_token}/pinChatMessage"
                    pin_payload = json.dumps({
                        "chat_id": admin_group_id,
                        "message_id": msg_id,
                        "disable_notification": True
                    }).encode("utf-8")
                    try:
                        urllib.request.urlopen(urllib.request.Request(pin_url, data=pin_payload, headers={"Content-Type": "application/json"}, method="POST"), timeout=4)
                    except Exception:
                        pass
        else:
            file_bytes = json_str.encode("utf-8")
            boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
            body = bytearray()
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{admin_group_id}\r\n'.encode("utf-8"))
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="caption"\r\n\r\n🤖 [BOT_DB_BACKUP]\r\n'.encode("utf-8"))
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="document"; filename="bot_data_backup.json"\r\n'.encode("utf-8"))
            body.extend(f'Content-Type: application/json\r\n\r\n'.encode("utf-8"))
            body.extend(file_bytes)
            body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))
            
            doc_url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
            req = urllib.request.Request(doc_url, data=bytes(body), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
            with urllib.request.urlopen(req, timeout=8) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("ok"):
                    msg_id = res["result"]["message_id"]
                    _telegram_backup_msg_id = msg_id
                    pin_url = f"https://api.telegram.org/bot{bot_token}/pinChatMessage"
                    pin_payload = json.dumps({
                        "chat_id": admin_group_id,
                        "message_id": msg_id,
                        "disable_notification": True
                    }).encode("utf-8")
                    try:
                        urllib.request.urlopen(urllib.request.Request(pin_url, data=pin_payload, headers={"Content-Type": "application/json"}, method="POST"), timeout=4)
                    except Exception:
                        pass
    except Exception:
        pass

def _get_json_db() -> Dict[str, Any]:
    default_db = {
        "settings": {},
        "teams": {},
        "stations": {},
        "routes": {},
        "user_progress": {}
    }
    env_json = os.getenv("BOT_DATA_JSON")
    if env_json:
        try:
            data = json.loads(env_json)
            if isinstance(data, dict):
                for k in default_db:
                    if k not in data:
                        data[k] = default_db[k]
                return data
        except Exception:
            pass

    # Check /tmp/bot_data.json first if it has dynamic data
    tmp_path = "/tmp/bot_data.json"
    if os.path.exists(tmp_path):
        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and (data.get("teams") or data.get("stations") or data.get("routes")):
                    for k in default_db:
                        if k not in data:
                            data[k] = default_db[k]
                    return data
        except Exception:
            pass

    # Fetch from Vercel KV / Upstash Redis
    kv_data = _fetch_kv_db()
    if kv_data and isinstance(kv_data, dict) and (kv_data.get("teams") or kv_data.get("routes") or kv_data.get("stations")):
        for k in default_db:
            if k not in kv_data:
                kv_data[k] = default_db[k]
        return kv_data

    # Fetch from Telegram Cloud Backup
    tg_data = _fetch_telegram_backup()
    if tg_data and isinstance(tg_data, dict) and (tg_data.get("teams") or tg_data.get("routes") or tg_data.get("stations")):
        for k in default_db:
            if k not in tg_data:
                tg_data[k] = default_db[k]
        return tg_data

    # Fallback to local files
    for path in JSON_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        for k in default_db:
                            if k not in data:
                                data[k] = default_db[k]
                        return data
            except Exception:
                pass

    return default_db

def _save_json_db(data: Dict[str, Any]):
    for path in JSON_PATHS:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    try:
        _save_kv_db(data)
    except Exception:
        pass
    try:
        _save_telegram_backup(data)
    except Exception:
        pass

def _sync_sqlite_to_json():
    if not HAS_SQLITE:
        return
    try:
        data = {
            "settings": {},
            "teams": {},
            "stations": {},
            "routes": {},
            "user_progress": {}
        }
        with _get_connection() as conn:
            s_rows = conn.execute("SELECT key, value FROM settings").fetchall()
            for r in s_rows:
                data["settings"][r["key"]] = r["value"]
            
            t_rows = conn.execute("SELECT * FROM teams").fetchall()
            for r in t_rows:
                data["teams"][r["team_id"]] = dict(r)
            
            st_rows = conn.execute("SELECT * FROM stations").fetchall()
            for r in st_rows:
                data["stations"][r["station_id"]] = dict(r)
            
            r_rows = conn.execute("SELECT team_id, station_id FROM routes ORDER BY team_id, station_order").fetchall()
            for r in r_rows:
                tid = r["team_id"]
                if tid not in data["routes"]:
                    data["routes"][tid] = []
                data["routes"][tid].append(r["station_id"])
            
            up_rows = conn.execute("SELECT * FROM user_progress").fetchall()
            for r in up_rows:
                data["user_progress"][str(r["user_id"])] = dict(r)
        
        _save_json_db(data)
    except Exception:
        pass

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
        cursor.execute("CREATE TABLE IF NOT EXISTS user_progress (user_id INTEGER PRIMARY KEY, team_id TEXT, current_index INTEGER DEFAULT 0, station_start_time REAL DEFAULT 0.0, status TEXT DEFAULT 'in_progress', finish_order INTEGER DEFAULT 0, keyword_attempts INTEGER DEFAULT 0)")
        
        try:
            cursor.execute("ALTER TABLE user_progress ADD COLUMN finish_order INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE user_progress ADD COLUMN keyword_attempts INTEGER DEFAULT 0")
        except Exception:
            pass
            
        conn.commit()
        
        # Check if SQLite tables are empty and restore from JSON backup if available
        try:
            t_count = cursor.execute("SELECT COUNT(*) as cnt FROM teams").fetchone()["cnt"]
            r_count = cursor.execute("SELECT COUNT(*) as cnt FROM routes").fetchone()["cnt"]
            
            if t_count == 0 and r_count == 0:
                json_db = _get_json_db()
                for k, v in json_db.get("settings", {}).items():
                    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
                for tid, tinfo in json_db.get("teams", {}).items():
                    cursor.execute("INSERT OR IGNORE INTO teams (team_id, user_id, username, full_name) VALUES (?, ?, ?, ?)",
                                   (tid, tinfo.get("user_id"), tinfo.get("username"), tinfo.get("full_name")))
                for sid, sinfo in json_db.get("stations", {}).items():
                    cursor.execute("INSERT OR IGNORE INTO stations (station_id, name) VALUES (?, ?)", (sid, sinfo.get("name")))
                for tid, st_list in json_db.get("routes", {}).items():
                    for idx, st_id in enumerate(st_list):
                        cursor.execute("INSERT OR IGNORE INTO stations (station_id) VALUES (?)", (st_id,))
                        cursor.execute("INSERT INTO routes (team_id, station_order, station_id) VALUES (?, ?, ?)", (tid, idx, st_id))
                for uid_str, pinfo in json_db.get("user_progress", {}).items():
                    cursor.execute("INSERT OR REPLACE INTO user_progress (user_id, team_id, current_index, station_start_time, status, finish_order, keyword_attempts) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                   (pinfo.get("user_id"), pinfo.get("team_id"), pinfo.get("current_index", 0), pinfo.get("station_start_time", 0.0), pinfo.get("status", "in_progress"), pinfo.get("finish_order", 0), pinfo.get("keyword_attempts", 0)))
                conn.commit()
        except Exception:
            pass

    _sync_sqlite_to_json()

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
    _sync_sqlite_to_json()

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
    _sync_sqlite_to_json()
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
    _sync_sqlite_to_json()
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
    _sync_sqlite_to_json()
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
        except sqlite3.IntegrityError:
            if name:
                conn.execute("UPDATE stations SET name = ? WHERE station_id = ?", (name, sid))
                conn.commit()
    _sync_sqlite_to_json()
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
    _sync_sqlite_to_json()
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
    _sync_sqlite_to_json()
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
    _sync_sqlite_to_json()
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
    _sync_sqlite_to_json()
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
    _sync_sqlite_to_json()

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
    _sync_sqlite_to_json()

async def set_user_status(user_id: int, status: str):
    await asyncio.to_thread(_set_user_status_sync, user_id, status)

def _stop_game_reset_sync(clear_participants: bool = False):
    if not HAS_SQLITE:
        db = _get_json_db()
        db["settings"]["game_started"] = "0"
        db["user_progress"] = {}
        if clear_participants:
            for tid in db["teams"]:
                db["teams"][tid]["user_id"] = None
                db["teams"][tid]["username"] = None
                db["teams"][tid]["full_name"] = None
        _save_json_db(db)
        return
    with _get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('game_started', '0')")
        conn.execute("DELETE FROM user_progress")
        if clear_participants:
            conn.execute("UPDATE teams SET user_id = NULL, username = NULL, full_name = NULL")
        conn.commit()
    _sync_sqlite_to_json()

async def stop_game_reset(clear_participants: bool = False):
    await asyncio.to_thread(_stop_game_reset_sync, clear_participants)

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
    _sync_sqlite_to_json()
    return True

async def clear_routes(team_id: Optional[str] = None) -> bool:
    return await asyncio.to_thread(_clear_routes_sync, team_id)

def _increment_keyword_attempts_sync(user_id: int) -> int:
    uid_str = str(user_id)
    if not HAS_SQLITE:
        db = _get_json_db()
        if uid_str in db["user_progress"]:
            attempts = db["user_progress"][uid_str].get("keyword_attempts", 0) + 1
            db["user_progress"][uid_str]["keyword_attempts"] = attempts
            _save_json_db(db)
            return attempts
        return 1

    with _get_connection() as conn:
        conn.execute("UPDATE user_progress SET keyword_attempts = COALESCE(keyword_attempts, 0) + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        row = conn.execute("SELECT keyword_attempts FROM user_progress WHERE user_id = ?", (user_id,)).fetchone()
        attempts = row["keyword_attempts"] if row and row["keyword_attempts"] is not None else 1
    _sync_sqlite_to_json()
    return attempts

async def increment_keyword_attempts(user_id: int) -> int:
    return await asyncio.to_thread(_increment_keyword_attempts_sync, user_id)

def _complete_user_quest_sync(user_id: int) -> Dict[str, Any]:
    uid_str = str(user_id)
    if not HAS_SQLITE:
        db = _get_json_db()
        max_order = max([p.get("finish_order", 0) for p in db["user_progress"].values()], default=0)
        next_order = max_order + 1
        if uid_str in db["user_progress"]:
            db["user_progress"][uid_str]["status"] = "completed"
            db["user_progress"][uid_str]["finish_order"] = next_order
            _save_json_db(db)
            return db["user_progress"][uid_str]
        return {"user_id": user_id, "status": "completed", "finish_order": next_order, "keyword_attempts": 1}

    with _get_connection() as conn:
        row_max = conn.execute("SELECT MAX(finish_order) as max_ord FROM user_progress WHERE status = 'completed'").fetchone()
        max_ord = row_max["max_ord"] if row_max and row_max["max_ord"] is not None else 0
        next_ord = max_ord + 1
        conn.execute("UPDATE user_progress SET status = 'completed', finish_order = ? WHERE user_id = ?", (next_ord, user_id))
        conn.commit()
        res = conn.execute("SELECT * FROM user_progress WHERE user_id = ?", (user_id,)).fetchone()
        res_dict = dict(res) if res else {"user_id": user_id, "finish_order": next_ord, "keyword_attempts": 1}
    _sync_sqlite_to_json()
    return res_dict

async def complete_user_quest(user_id: int) -> Dict[str, Any]:
    return await asyncio.to_thread(_complete_user_quest_sync, user_id)

def _get_leaderboard_sync() -> List[Dict[str, Any]]:
    if not HAS_SQLITE:
        db = _get_json_db()
        completed_list = [p for p in db["user_progress"].values() if p.get("status") == "completed"]
        completed_list.sort(key=lambda x: x.get("finish_order", 999))
        return completed_list

    with _get_connection() as conn:
        rows = conn.execute("SELECT * FROM user_progress WHERE status = 'completed' ORDER BY finish_order ASC").fetchall()
        return [dict(r) for r in rows]

async def get_leaderboard() -> List[Dict[str, Any]]:
    return await asyncio.to_thread(_get_leaderboard_sync)

def _check_all_teams_completed_sync() -> bool:
    if not HAS_SQLITE:
        db = _get_json_db()
        occupied_user_ids = [t["user_id"] for t in db["teams"].values() if t.get("user_id") is not None]
        if not occupied_user_ids:
            return False
        for uid in occupied_user_ids:
            p = db["user_progress"].get(str(uid))
            if not p or p.get("status") != "completed":
                return False
        return True

    with _get_connection() as conn:
        occupied = conn.execute("SELECT user_id FROM teams WHERE user_id IS NOT NULL").fetchall()
        if not occupied:
            return False
        for r in occupied:
            uid = r["user_id"]
            p = conn.execute("SELECT status FROM user_progress WHERE user_id = ?", (uid,)).fetchone()
            if not p or p["status"] != "completed":
                return False
        return True

async def check_all_teams_completed() -> bool:
    return await asyncio.to_thread(_check_all_teams_completed_sync)

def _force_skip_user_station_sync(team_id_or_user_id: Any) -> Optional[Dict[str, Any]]:
    target_user_id = None
    if isinstance(team_id_or_user_id, int):
        target_user_id = team_id_or_user_id
    else:
        tid_str = str(team_id_or_user_id).strip()
        if tid_str.isdigit() and len(tid_str) > 6:
            target_user_id = int(tid_str)
        else:
            team = _get_team_sync(tid_str)
            if team and team.get("user_id"):
                target_user_id = team["user_id"]

    if not target_user_id:
        return None

    progress = _get_user_progress_sync(target_user_id)
    if not progress or progress.get("status") != "in_progress":
        return None

    team_id = progress["team_id"]
    route = _get_route_sync(team_id)
    if not route:
        return None

    curr_index = progress["current_index"]
    next_index = curr_index + 1
    now_time = time.time()

    if next_index < len(route):
        _advance_user_station_sync(target_user_id, next_index, now_time)
        next_st_id = route[next_index]["station_id"]
        st_info = _get_station_sync(next_st_id)
        st_name = st_info["name"] if st_info and st_info.get("name") else next_st_id
        return {
            "user_id": target_user_id,
            "team_id": team_id,
            "status": "in_progress",
            "next_station_id": next_st_id,
            "next_station_name": st_name
        }
    else:
        _set_user_status_sync(target_user_id, "waiting_final_word")
        return {
            "user_id": target_user_id,
            "team_id": team_id,
            "status": "waiting_final_word"
        }

async def force_skip_user_station(team_id_or_user_id: Any) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(_force_skip_user_station_sync, team_id_or_user_id)


