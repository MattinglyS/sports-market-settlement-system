# ============================================================
# Automated Sports Market Settlement System
# Author: Mattingly Siegel
# Description: Single-script automated settlement workflow.
# Automatically stores contract lines in a local SQLite
# database so they are never lost even after games start.
# Works correctly at any time of day from any timezone.
# Uses three live data sources:
# - The Odds API for real consensus over/under lines
# - nba_api for real final and live game scores
# - TheSportsDB for venue and location data
# All decisions logged for CFTC compliance.
# ============================================================

import requests
import datetime
import pandas as pd
import pytz
from nba_api.stats.endpoints import scoreboardv3
from db import init_db, store_contracts, load_todays_contracts, has_todays_contracts, load_recent_contracts

ODDS_API_KEY = "9d8da42a565270cdd585078555d5f310"
EASTERN = pytz.timezone("America/New_York")

# ============================================================
# SECTION 1: ODDS API
# Pulls all upcoming NBA games with consensus lines.
# Only called if today's contracts aren't stored yet.
# ============================================================
def get_all_odds():
    try:
        response = requests.get(
            "https://api.the-odds-api.com/v4/sports/basketball_nba/odds",
            params={
                "apiKey": ODDS_API_KEY,
                "regions": "us",
                "markets": "totals",
                "oddsFormat": "american"
            },
            timeout=10
        )
        data = response.json()
        today = datetime.date.today()
        contracts = {}
        for game in data:
            home = game['home_team']
            away = game['away_team']
            game_time_utc = datetime.datetime.fromisoformat(
                game['commence_time'].replace('Z', '+00:00')
            )
            game_time_et = game_time_utc.astimezone(EASTERN)

            # Only store today's games
            if game_time_et.date() != today:
                continue

            lines = []
            for bookmaker in game['bookmakers']:
                for market in bookmaker['markets']:
                    if market['key'] == 'totals':
                        for outcome in market['outcomes']:
                            if outcome['name'] == 'Over':
                                lines.append(outcome['point'])
            if lines:
                consensus = round(sum(lines) / len(lines), 1)
                game_key = f"{away} @ {home}"
                contracts[game_key] = {
                    "home": home,
                    "away": away,
                    "threshold": consensus,
                    "volume": 50000,
                    "game_time": game_time_et,
                    "sport": "NBA"
                }
        return contracts
    except Exception as e:
        print(f"WARNING: Could not retrieve odds. Error: {e}")
        return {}

# ============================================================
# SECTION 2: ODDS API — TOMORROW'S GAMES
# Pulls tomorrow's games for preview section.
# ============================================================
def get_tomorrows_games():
    try:
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        response = requests.get(
            "https://api.the-odds-api.com/v4/sports/basketball_nba/odds",
            params={
                "apiKey": ODDS_API_KEY,
                "regions": "us",
                "markets": "totals",
                "oddsFormat": "american"
            },
            timeout=10
        )
        data = response.json()
        tomorrow_games = {}
        for game in data:
            home = game['home_team']
            away = game['away_team']
            game_time_utc = datetime.datetime.fromisoformat(
                game['commence_time'].replace('Z', '+00:00')
            )
            game_time_et = game_time_utc.astimezone(EASTERN)
            if game_time_et.date() != tomorrow:
                continue
            game_key = f"{away} @ {home}"
            lines = []
            for bookmaker in game['bookmakers']:
                for market in bookmaker['markets']:
                    if market['key'] == 'totals':
                        for outcome in market['outcomes']:
                            if outcome['name'] == 'Over':
                                lines.append(outcome['point'])
            if lines:
                tomorrow_games[game_key] = {
                    "threshold": round(sum(lines) / len(lines), 1),
                    "game_time": game_time_et
                }
        return tomorrow_games
    except Exception as e:
        print(f"WARNING: Could not retrieve tomorrow's odds. Error: {e}")
        return {}

# ============================================================
# SECTION 3: NBA API — FULL SCHEDULE & SCORES
# Pulls ALL of today's games from nba_api.
# Never misses a game regardless of when script is run.
# ============================================================
def get_todays_games():
    try:
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        games = {}

        for check_date in [yesterday, today]:
            data = scoreboardv3.ScoreboardV3(game_date=check_date).get_dict()
            for game in data['scoreboard']['games']:
                status = game['gameStatusText'].strip()
                home = game['homeTeam']
                away = game['awayTeam']
                home_name = f"{home['teamCity']} {home['teamName']}"
                away_name = f"{away['teamCity']} {away['teamName']}"
                game_key = f"{away_name} @ {home_name}"

                game_time_utc = datetime.datetime.fromisoformat(
                    game['gameTimeUTC'].replace('Z', '+00:00')
                )
                game_time_et = game_time_utc.astimezone(EASTERN)

                if game_time_et.date() != today:
                    continue

                entry = {
                    "home": home_name,
                    "away": away_name,
                    "game_time": game_time_et,
                    "status": status,
                    "game_status_id": game['gameStatus'],
                    "home_score": home['score'] or 0,
                    "away_score": away['score'] or 0,
                    "combined": (home['score'] or 0) + (away['score'] or 0)
                }

                if game_key not in games or status.startswith("Final"):
                    games[game_key] = entry

        return games
    except Exception as e:
        print(f"WARNING: Could not retrieve NBA schedule. Error: {e}")
        return {}

# ============================================================
# SECTION 4: THESPORTSDB — VENUE DATA
# ============================================================
def get_nba_teams():
    try:
        response = requests.get(
            "https://www.thesportsdb.com/api/v1/json/3/search_all_teams.php?l=NBA",
            timeout=10
        )
        data = response.json()
        teams = {}
        for team in data["teams"]:
            teams[team["strTeam"]] = {
                "stadium": team["strStadium"],
                "location": team["strLocation"]
            }
        return teams
    except Exception:
        print("WARNING: Could not reach TheSportsDB API.")
        return {}
def get_historical_scores(date_str):
        try:
            check_date = datetime.date.fromisoformat(date_str)
            data = scoreboardv3.ScoreboardV3(game_date=check_date).get_dict()
            scores = {}
            for game in data['scoreboard']['games']:
                status = game['gameStatusText'].strip()
                home = game['homeTeam']
                away = game['awayTeam']
                home_name = f"{home['teamCity']} {home['teamName']}"
                away_name = f"{away['teamCity']} {away['teamName']}"
                game_key = f"{away_name} @ {home_name}"
                if status.startswith("Final"):
                    scores[game_key] = {
                        "home_score": home['score'] or 0,
                        "away_score": away['score'] or 0,
                        "combined": (home['score'] or 0) + (away['score'] or 0),
                        "status": status
                    }
            return scores
        except Exception as e:
            print(f"WARNING: Could not retrieve scores for {date_str}: {e}")
            return {}
            
# ============================================================
# SECTION 5: SETTLEMENT FUNCTION
# ============================================================
def settle_contract(game_key, game_data, threshold, stadium, location, volume):
    timestamp = datetime.datetime.now(EASTERN)
    now_et = datetime.datetime.now(EASTERN)
    status = game_data['status']
    game_time = game_data['game_time']

    if status.startswith("Final"):
        try:
            combined = int(game_data["combined"])
            if combined > threshold:
                result = "OVER"
            elif combined == threshold:
                result = "PUSH"
            else:
                result = "UNDER"
            display_score = f"{game_data['away_score']}-{game_data['home_score']} (Total: {combined})"
        except (ValueError, TypeError, KeyError):
            result = "ERROR - Needs manual review"
            display_score = "Unknown"

    elif game_data['game_status_id'] == 2:
        combined = game_data["combined"]
        display_score = f"{game_data['away_score']}-{game_data['home_score']} (Total: {combined})"
        result = f"IN PROGRESS - {status}"

    elif game_time and game_time > now_et:
        time_until = game_time - now_et
        hours = int(time_until.total_seconds() // 3600)
        minutes = int((time_until.total_seconds() % 3600) // 60)
        tipoff_str = game_time.strftime("%I:%M %p ET")
        result = f"UPCOMING - Tipoff at {tipoff_str} ({hours}h {minutes}m)"
        display_score = "Not yet played"

    else:
        result = "ERROR - Needs manual review"
        display_score = "Unknown"

    log_entry = f"{timestamp.strftime('%Y-%m-%d %I:%M %p ET')} | {game_key} | {stadium} | {location} | Score: {display_score} | Line: {threshold} | Volume: ${volume:,} | Result: {result}"

    with open("capstone_log.txt", "a") as log_file:
        log_file.write(log_entry + "\n")

    return result, display_score

# ============================================================
# SECTION 6: MAIN SETTLEMENT LOOP
# ============================================================
start_time = datetime.datetime.now(EASTERN)

print("=" * 55)
print("  NBA SETTLEMENT SYSTEM")
print(f"  Date: {start_time.strftime('%B %d, %Y')}")
print(f"  Time: {start_time.strftime('%I:%M %p ET')}")
print("=" * 55)

# Initialize database
init_db()

# Pull today's full game schedule from nba_api
todays_games = get_todays_games()

# Check if we already have today's lines stored
if has_todays_contracts():
    stored_contracts = load_todays_contracts()
    new_contracts = get_all_odds()
    # Store any new games not already in database
    if new_contracts:
        newly_stored = store_contracts(new_contracts)
        if newly_stored > 0:
            stored_contracts = load_todays_contracts()
    contracts = stored_contracts
    print(f"\n📋 Lines loaded from database")
else:
    # First run today — pull and store all lines
    new_contracts = get_all_odds()
    if new_contracts:
        store_contracts(new_contracts)
        print(f"\n📋 Lines pulled from odds API and stored")
    contracts = load_todays_contracts()

tomorrow_games = get_tomorrows_games()
nba_teams = get_nba_teams()

print(f"📊 TODAY'S GAMES: {len(todays_games)}")
print(f"🏀 CONTRACTS WITH LINES: {len(contracts)}")
print(f"📅 TOMORROW'S GAMES: {len(tomorrow_games)}")

results = []
settled_list = []
in_progress_list = []
upcoming_list = []
errors_list = []
no_line_list = []

VOLUME = 50000

for game_key, game_data in todays_games.items():
    home = game_data['home']

    if nba_teams and home in nba_teams:
        stadium = nba_teams[home]["stadium"]
        location = nba_teams[home]["location"]
    else:
        stadium = "Unknown"
        location = "Unknown"

    if game_key in contracts:
        threshold = contracts[game_key]['threshold']
        volume = contracts[game_key]['volume']

        result, display_score = settle_contract(
            game_key, game_data, threshold, stadium, location, volume
        )

        entry = {
            "game": game_key,
            "stadium": stadium,
            "location": location,
            "score": display_score,
            "line": threshold,
            "volume": volume,
            "result": result,
        }
        results.append(entry)

        if result in ["OVER", "UNDER", "PUSH"]:
            settled_list.append(entry)
        elif result.startswith("IN PROGRESS"):
            in_progress_list.append(entry)
        elif result.startswith("UPCOMING"):
            upcoming_list.append(entry)
        else:
            errors_list.append(entry)

    else:
        # No line available — show score only
        status = game_data['status']
        if status.startswith("Final"):
            combined = game_data["combined"]
            display_score = f"{game_data['away_score']}-{game_data['home_score']} (Total: {combined})"
        elif game_data['game_status_id'] == 2:
            combined = game_data["combined"]
            display_score = f"{game_data['away_score']}-{game_data['home_score']} (Total: {combined})"
        else:
            display_score = "Not yet played"

        entry = {
            "game": game_key,
            "stadium": stadium,
            "location": location,
            "score": display_score,
            "line": "N/A",
            "volume": 0,
            "result": "NO LINE",
        }
        results.append(entry)
        no_line_list.append(entry)

# ============================================================
# SECTION 7: CLEAN OUTPUT DISPLAY
# ============================================================
if settled_list:
    print("\n" + "-" * 55)
    print("  ✅ SETTLED CONTRACTS")
    print("-" * 55)
    for e in settled_list:
        print(f"  {e['game']:<38} | {e['score']:<25} | Line: {e['line']:<6} | {e['result']:<6} | ${e['volume']:,}")

if in_progress_list:
    print("\n" + "-" * 55)
    print("  🔴 IN PROGRESS")
    print("-" * 55)
    for e in in_progress_list:
        status_short = e['result'].replace("IN PROGRESS - ", "")
        print(f"  {e['game']:<38} | {e['score']:<25} | Line: {e['line']:<6} | {status_short}")

if upcoming_list:
    print("\n" + "-" * 55)
    print("  ⏰ UPCOMING CONTRACTS")
    print("-" * 55)
    for e in upcoming_list:
        tipoff = e['result'].replace("UPCOMING - ", "")
        print(f"  {e['game']:<38} | Line: {e['line']:<6} | {tipoff}")

if no_line_list:
    print("\n" + "-" * 55)
    print("  📊 FINAL SCORES — NO LINE AVAILABLE")
    print("-" * 55)
    for e in no_line_list:
        print(f"  {e['game']:<38} | {e['score']:<25}")

if errors_list:
    print("\n" + "-" * 55)
    print("  ⚠️  MANUAL REVIEW REQUIRED")
    print("-" * 55)
    for e in errors_list:
        print(f"  {e['game']:<38} | Line: {e['line']}")

if tomorrow_games:
    print("\n" + "-" * 55)
    print("  📅 TOMORROW'S GAMES")
    print("-" * 55)
    for game_key, data in tomorrow_games.items():
        tipoff = data['game_time'].strftime("%I:%M %p ET")
        print(f"  {game_key:<38} | Line: {data['threshold']:<6} | Tipoff: {tipoff}")

# ============================================================
# SECTION 8: SUMMARY
# ============================================================
settled_vol = sum(e['volume'] for e in settled_list)
in_progress_vol = sum(e['volume'] for e in in_progress_list)
upcoming_vol = sum(e['volume'] for e in upcoming_list)
total_vol = settled_vol + in_progress_vol + upcoming_vol

end_time = datetime.datetime.now(EASTERN)
duration = (end_time - start_time).total_seconds()

print("\n" + "=" * 55)
print("  SUMMARY")
print("-" * 55)
print(f"  Settled:     {len(settled_list):<4} | Volume: ${settled_vol:,}")
print(f"  In Progress: {len(in_progress_list):<4} | Volume: ${in_progress_vol:,}")
print(f"  Upcoming:    {len(upcoming_list):<4} | Volume: ${upcoming_vol:,}")
if no_line_list:
    print(f"  No Line:     {len(no_line_list):<4} | (final scores shown)")
if errors_list:
    print(f"  Errors:      {len(errors_list):<4} | Volume: $0")
print(f"  {'─' * 40}")
print(f"  Total Games: {len(todays_games):<4} | Volume: ${total_vol:,}")
print(f"\n  Run completed in {duration:.2f} seconds")

if errors_list:
    df_errors = pd.DataFrame(errors_list)
    df_errors.to_csv("manual_review.csv", index=False)
    print(f"\n  ⚠️  {len(errors_list)} contract(s) saved to manual_review.csv")
else:
    print("\n  ✅ No manual review required!")
# ============================================================
# SECTION 9: HISTORICAL SETTLEMENTS
# Shows last 3 days of settled contracts
# ============================================================
recent_contracts = load_recent_contracts(days=3)

if recent_contracts:
    print("\n" + "-" * 55)
    print("  📜 RECENT SETTLEMENTS (LAST 3 DAYS)")
    print("-" * 55)

    for date_str, day_contracts in sorted(recent_contracts.items(), reverse=True):
        date_display = datetime.date.fromisoformat(date_str).strftime("%B %d, %Y")
        print(f"\n  {date_display}")
        print(f"  {'─' * 50}")

        historical_scores = get_historical_scores(date_str)

        for game_key, contract in day_contracts.items():
            threshold = contract['threshold']
            score_data = historical_scores.get(game_key)

            if score_data:
                combined = score_data['combined']
                if combined > threshold:
                    result = "OVER"
                elif combined == threshold:
                    result = "PUSH"
                else:
                    result = "UNDER"
                display_score = f"{score_data['away_score']}-{score_data['home_score']} (Total: {combined})"
                print(f"  ✅ {game_key:<38} | {display_score:<25} | Line: {threshold:<6} | {result}")
            else:
                print(f"  ⏭️  {game_key:<38} | No final score available")
                
print("=" * 55)
