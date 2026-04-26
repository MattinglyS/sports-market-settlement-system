# ============================================================
# Database Module
# Handles storing and retrieving contract lines using SQLite.
# Auto-creates database on first run.
# Lines are stored before games start so they're never lost.
# ============================================================

import sqlite3
import datetime
import pytz

EASTERN = pytz.timezone("America/New_York")
DB_FILE = "settlement.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            game_key TEXT,
            game_date TEXT,
            home TEXT,
            away TEXT,
            threshold REAL,
            volume INTEGER,
            game_time TEXT,
            sport TEXT,
            created TEXT,
            PRIMARY KEY (game_key, game_date)
        )
    """)
    conn.commit()
    conn.close()

def store_contracts(contracts):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today = datetime.date.today().isoformat()
    stored = 0
    for game_key, contract in contracts.items():
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO contracts 
                (game_key, game_date, home, away, threshold, volume, game_time, sport, created)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                game_key,
                today,
                contract['home'],
                contract['away'],
                contract['threshold'],
                contract['volume'],
                contract['game_time'].strftime("%Y-%m-%d %I:%M %p ET"),
                contract['sport'],
                datetime.datetime.now(EASTERN).strftime("%Y-%m-%d %I:%M %p ET")
            ))
            if cursor.rowcount > 0:
                stored += 1
        except Exception as e:
            print(f"WARNING: Could not store contract {game_key}: {e}")
    conn.commit()
    conn.close()
    return stored

def load_todays_contracts():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today = datetime.date.today().isoformat()
    cursor.execute("""
        SELECT game_key, home, away, threshold, volume, game_time, sport
        FROM contracts
        WHERE game_date = ?
    """, (today,))
    rows = cursor.fetchall()
    conn.close()

    contracts = {}
    for row in rows:
        game_key, home, away, threshold, volume, game_time_str, sport = row
        game_time = EASTERN.localize(
            datetime.datetime.strptime(game_time_str, "%Y-%m-%d %I:%M %p ET")
        )
        contracts[game_key] = {
            "home": home,
            "away": away,
            "threshold": threshold,
            "volume": volume,
            "game_time": game_time,
            "sport": sport
        }
    return contracts

def has_todays_contracts():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today = datetime.date.today().isoformat()
    cursor.execute("SELECT COUNT(*) FROM contracts WHERE game_date = ?", (today,))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0
def load_recent_contracts(days=3):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today = datetime.date.today()
    contracts_by_date = {}

    for i in range(1, days + 1):
        date = (today - datetime.timedelta(days=i)).isoformat()
        cursor.execute("""
            SELECT game_key, home, away, threshold, volume, game_time, sport
            FROM contracts
            WHERE game_date = ?
        """, (date,))
        rows = cursor.fetchall()
        if rows:
            contracts_by_date[date] = {}
            for row in rows:
                game_key, home, away, threshold, volume, game_time_str, sport = row
                game_time = EASTERN.localize(
                    datetime.datetime.strptime(game_time_str, "%Y-%m-%d %I:%M %p ET")
                )
                contracts_by_date[date][game_key] = {
                    "home": home,
                    "away": away,
                    "threshold": threshold,
                    "volume": volume,
                    "game_time": game_time,
                    "sport": sport
                }

    conn.close()
    return contracts_by_date
