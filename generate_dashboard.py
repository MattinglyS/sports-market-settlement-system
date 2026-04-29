# ============================================================
# NBA Settlement Dashboard Generator
# Author: Mattingly Siegel
# Description: Generates a professional HTML dashboard
# showing live NBA settlement data. Run this script to
# open the dashboard automatically in your browser.
# ============================================================

import requests
import datetime
import pandas as pd
import pytz
import webbrowser
import os
from nba_api.stats.endpoints import scoreboardv3
from db import init_db, store_contracts, load_todays_contracts, has_todays_contracts, load_recent_contracts

ODDS_API_KEY = "9d8da42a565270cdd585078555d5f310"
EASTERN = pytz.timezone("America/New_York")

# ============================================================
# DATA FUNCTIONS — same logic as settlement_system.py
# ============================================================
def get_all_odds():
    try:
        response = requests.get(
            "https://api.the-odds-api.com/v4/sports/basketball_nba/odds",
            params={"apiKey": ODDS_API_KEY, "regions": "us", "markets": "totals", "oddsFormat": "american"},
            timeout=10
        )
        data = response.json()
        today = datetime.date.today()
        contracts = {}
        for game in data:
            home = game['home_team']
            away = game['away_team']
            game_time_utc = datetime.datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00'))
            game_time_et = game_time_utc.astimezone(EASTERN)
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
                game_key = f"{away} @ {home}"
                contracts[game_key] = {
                    "home": home, "away": away,
                    "threshold": round(sum(lines) / len(lines), 1),
                    "volume": 50000, "game_time": game_time_et, "sport": "NBA"
                }
        return contracts
    except Exception as e:
        return {}

def get_tomorrows_games():
    try:
        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        response = requests.get(
            "https://api.the-odds-api.com/v4/sports/basketball_nba/odds",
            params={"apiKey": ODDS_API_KEY, "regions": "us", "markets": "totals", "oddsFormat": "american"},
            timeout=10
        )
        data = response.json()
        tomorrow_games = {}
        for game in data:
            home = game['home_team']
            away = game['away_team']
            game_time_utc = datetime.datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00'))
            game_time_et = game_time_utc.astimezone(EASTERN)
            if game_time_et.date() != tomorrow:
                continue
            lines = []
            for bookmaker in game['bookmakers']:
                for market in bookmaker['markets']:
                    if market['key'] == 'totals':
                        for outcome in market['outcomes']:
                            if outcome['name'] == 'Over':
                                lines.append(outcome['point'])
            if lines:
                tomorrow_games[f"{away} @ {home}"] = {
                    "threshold": round(sum(lines) / len(lines), 1),
                    "game_time": game_time_et
                }
        return tomorrow_games
    except:
        return {}

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
                game_time_utc = datetime.datetime.fromisoformat(game['gameTimeUTC'].replace('Z', '+00:00'))
                game_time_et = game_time_utc.astimezone(EASTERN)
                if game_time_et.date() != today:
                    continue
                entry = {
                    "home": home_name, "away": away_name,
                    "game_time": game_time_et, "status": status,
                    "game_status_id": game['gameStatus'],
                    "home_score": home['score'] or 0,
                    "away_score": away['score'] or 0,
                    "combined": (home['score'] or 0) + (away['score'] or 0)
                }
                if game_key not in games or status.startswith("Final"):
                    games[game_key] = entry
        return games
    except Exception as e:
        return {}

def get_nba_teams():
    try:
        response = requests.get(
            "https://www.thesportsdb.com/api/v1/json/3/search_all_teams.php?l=NBA",
            timeout=10
        )
        data = response.json()
        return {team["strTeam"]: {"stadium": team["strStadium"], "location": team["strLocation"]} for team in data["teams"]}
    except:
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
    except:
        return {}

# ============================================================
# SETTLEMENT LOGIC
# ============================================================
def process_settlements():
    init_db()
    todays_games = get_todays_games()

    if has_todays_contracts():
        contracts = load_todays_contracts()
        new_contracts = get_all_odds()
        if new_contracts:
            store_contracts(new_contracts)
            contracts = load_todays_contracts()
    else:
        new_contracts = get_all_odds()
        if new_contracts:
            store_contracts(new_contracts)
        contracts = load_todays_contracts()

    tomorrow_games = get_tomorrows_games()
    nba_teams = get_nba_teams()
    recent_contracts = load_recent_contracts(days=3)
    now_et = datetime.datetime.now(EASTERN)

    settled = []
    in_progress = []
    upcoming = []
    no_line = []

    for game_key, game_data in todays_games.items():
        home = game_data['home']
        stadium = nba_teams.get(home, {}).get("stadium", "Unknown")
        location = nba_teams.get(home, {}).get("location", "Unknown")
        status = game_data['status']
        game_time = game_data['game_time']

        if game_key in contracts:
            threshold = contracts[game_key]['threshold']
            volume = contracts[game_key]['volume']

            if status.startswith("Final"):
                combined = game_data["combined"]
                result = "OVER" if combined > threshold else ("PUSH" if combined == threshold else "UNDER")
                settled.append({
                    "game": game_key, "stadium": stadium, "location": location,
                    "away_score": game_data['away_score'], "home_score": game_data['home_score'],
                    "combined": combined, "threshold": threshold, "volume": volume, "result": result
                })
            elif game_data['game_status_id'] == 2:
                in_progress.append({
                    "game": game_key, "stadium": stadium, "location": location,
                    "away_score": game_data['away_score'], "home_score": game_data['home_score'],
                    "combined": game_data['combined'], "threshold": threshold,
                    "volume": volume, "status": status
                })
            elif game_time > now_et:
                time_until = game_time - now_et
                hours = int(time_until.total_seconds() // 3600)
                minutes = int((time_until.total_seconds() % 3600) // 60)
                upcoming.append({
                    "game": game_key, "stadium": stadium, "location": location,
                    "threshold": threshold, "volume": volume,
                    "tipoff": game_time.strftime("%I:%M %p ET"),
                    "countdown": f"{hours}h {minutes}m"
                })
        else:
            if status.startswith("Final"):
                no_line.append({
                    "game": game_key,
                    "away_score": game_data['away_score'],
                    "home_score": game_data['home_score'],
                    "combined": game_data['combined']
                })

    # Historical settlements
    history = []
    for date_str, day_contracts in sorted(recent_contracts.items(), reverse=True):
        historical_scores = get_historical_scores(date_str)
        date_display = datetime.date.fromisoformat(date_str).strftime("%B %d, %Y")
        day_results = []
        for game_key, contract in day_contracts.items():
            threshold = contract['threshold']
            score_data = historical_scores.get(game_key)
            if score_data:
                combined = score_data['combined']
                result = "OVER" if combined > threshold else ("PUSH" if combined == threshold else "UNDER")
                day_results.append({
                    "game": game_key,
                    "away_score": score_data['away_score'],
                    "home_score": score_data['home_score'],
                    "combined": combined,
                    "threshold": threshold,
                    "result": result
                })
        if day_results:
            history.append({"date": date_display, "games": day_results})

    return {
        "settled": settled,
        "in_progress": in_progress,
        "upcoming": upcoming,
        "no_line": no_line,
        "tomorrow": tomorrow_games,
        "history": history,
        "generated_at": now_et.strftime("%B %d, %Y at %I:%M %p ET")
    }

# ============================================================
# HTML DASHBOARD GENERATOR
# ============================================================
def generate_html(data):
    def result_color(result):
        if result == "OVER": return "#22c55e"
        if result == "UNDER": return "#ef4444"
        if result == "PUSH": return "#f59e0b"
        return "#94a3b8"

    def result_bg(result):
        if result == "OVER": return "rgba(34,197,94,0.1)"
        if result == "UNDER": return "rgba(239,68,68,0.1)"
        if result == "PUSH": return "rgba(245,158,11,0.1)"
        return "rgba(148,163,184,0.1)"

    # Build settled cards
    settled_html = ""
    for g in data['settled']:
        color = result_color(g['result'])
        bg = result_bg(g['result'])
        settled_html += f"""
        <div class="card" style="border-left: 3px solid {color}; background: {bg}">
            <div class="card-header">
                <span class="game-name">{g['game']}</span>
                <span class="result-badge" style="color:{color}; border-color:{color}">{g['result']}</span>
            </div>
            <div class="card-body">
                <div class="stat"><span class="stat-label">Score</span><span class="stat-value">{g['away_score']} - {g['home_score']}</span></div>
                <div class="stat"><span class="stat-label">Combined</span><span class="stat-value">{g['combined']}</span></div>
                <div class="stat"><span class="stat-label">Line</span><span class="stat-value">{g['threshold']}</span></div>
                <div class="stat"><span class="stat-label">Volume</span><span class="stat-value">${g['volume']:,}</span></div>
            </div>
            <div class="venue">{g['stadium']} — {g['location']}</div>
        </div>"""

    # Build in progress cards
    in_progress_html = ""
    for g in data['in_progress']:
        in_progress_html += f"""
        <div class="card live-card">
            <div class="live-indicator"><span class="live-dot"></span>LIVE</div>
            <div class="card-header">
                <span class="game-name">{g['game']}</span>
                <span class="status-badge">{g['status']}</span>
            </div>
            <div class="card-body">
                <div class="stat"><span class="stat-label">Current Score</span><span class="stat-value">{g['away_score']} - {g['home_score']}</span></div>
                <div class="stat"><span class="stat-label">Running Total</span><span class="stat-value">{g['combined']}</span></div>
                <div class="stat"><span class="stat-label">Line</span><span class="stat-value">{g['threshold']}</span></div>
                <div class="stat"><span class="stat-label">Pace</span><span class="stat-value">{'OVER' if g['combined'] > g['threshold'] else 'UNDER'}</span></div>
            </div>
            <div class="venue">{g['stadium']} — {g['location']}</div>
        </div>"""

    # Build upcoming cards
    upcoming_html = ""
    for g in data['upcoming']:
        upcoming_html += f"""
        <div class="card upcoming-card">
            <div class="card-header">
                <span class="game-name">{g['game']}</span>
                <span class="countdown-badge">{g['countdown']}</span>
            </div>
            <div class="card-body">
                <div class="stat"><span class="stat-label">Tipoff</span><span class="stat-value">{g['tipoff']}</span></div>
                <div class="stat"><span class="stat-label">Line</span><span class="stat-value">{g['threshold']}</span></div>
                <div class="stat"><span class="stat-label">Volume</span><span class="stat-value">${g['volume']:,}</span></div>
            </div>
            <div class="venue">{g['stadium']} — {g['location']}</div>
        </div>"""

    # Build no line cards
    no_line_html = ""
    for g in data['no_line']:
        no_line_html += f"""
        <div class="card no-line-card">
            <div class="card-header">
                <span class="game-name">{g['game']}</span>
                <span class="no-line-badge">NO LINE</span>
            </div>
            <div class="card-body">
                <div class="stat"><span class="stat-label">Final Score</span><span class="stat-value">{g['away_score']} - {g['home_score']}</span></div>
                <div class="stat"><span class="stat-label">Combined</span><span class="stat-value">{g['combined']}</span></div>
            </div>
        </div>"""

    # Build tomorrow cards
    tomorrow_html = ""
    for game_key, g in data['tomorrow'].items():
        tipoff = g['game_time'].strftime("%I:%M %p ET")
        tomorrow_html += f"""
        <div class="card tomorrow-card">
            <div class="card-header">
                <span class="game-name">{game_key}</span>
            </div>
            <div class="card-body">
                <div class="stat"><span class="stat-label">Tipoff</span><span class="stat-value">{tipoff}</span></div>
                <div class="stat"><span class="stat-label">Line</span><span class="stat-value">{g['threshold']}</span></div>
            </div>
        </div>"""

    # Build history section
    history_html = ""
    for day in data['history']:
        games_html = ""
        for g in day['games']:
            color = result_color(g['result'])
            games_html += f"""
            <div class="history-row">
                <span class="history-game">{g['game']}</span>
                <span class="history-score">{g['away_score']}-{g['home_score']} (Total: {g['combined']})</span>
                <span class="history-line">Line: {g['threshold']}</span>
                <span class="history-result" style="color:{color}">{g['result']}</span>
            </div>"""
        history_html += f"""
        <div class="history-day">
            <div class="history-date">{day['date']}</div>
            {games_html}
        </div>"""

    # Summary stats
    total_settled = len(data['settled'])
    total_in_progress = len(data['in_progress'])
    total_upcoming = len(data['upcoming'])
    total_volume = sum(g['volume'] for g in data['settled'] + data['in_progress'] + data['upcoming'])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NBA Settlement System</title>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{
            background: #0a0e1a;
            color: #e2e8f0;
            font-family: 'IBM Plex Sans', sans-serif;
            min-height: 100vh;
            padding: 0;
        }}

        .header {{
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            border-bottom: 1px solid #1e3a5f;
            padding: 24px 40px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .header-left h1 {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 22px;
            font-weight: 600;
            color: #f8fafc;
            letter-spacing: -0.5px;
        }}

        .header-left p {{
            font-size: 13px;
            color: #64748b;
            margin-top: 4px;
            font-family: 'IBM Plex Mono', monospace;
        }}

        .header-right {{
            display: flex;
            gap: 24px;
        }}

        .stat-pill {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 10px 20px;
            text-align: center;
        }}

        .stat-pill .number {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 20px;
            font-weight: 600;
            color: #38bdf8;
        }}

        .stat-pill .label {{
            font-size: 11px;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: 2px;
        }}

        .content {{
            padding: 32px 40px;
            max-width: 1400px;
            margin: 0 auto;
        }}

        .section {{
            margin-bottom: 40px;
        }}

        .section-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 16px;
            padding-bottom: 10px;
            border-bottom: 1px solid #1e293b;
        }}

        .section-title {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 13px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 2px;
            color: #94a3b8;
        }}

        .section-count {{
            background: #1e293b;
            color: #64748b;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 4px;
        }}

        .cards-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
            gap: 16px;
        }}

        .card {{
            background: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 20px;
            transition: transform 0.2s, border-color 0.2s;
        }}

        .card:hover {{
            transform: translateY(-2px);
            border-color: #334155;
        }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 16px;
            gap: 12px;
        }}

        .game-name {{
            font-size: 14px;
            font-weight: 500;
            color: #f1f5f9;
            line-height: 1.4;
        }}

        .result-badge {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 6px;
            border: 1px solid;
            white-space: nowrap;
        }}

        .status-badge {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11px;
            color: #f59e0b;
            background: rgba(245,158,11,0.1);
            padding: 4px 10px;
            border-radius: 6px;
            white-space: nowrap;
        }}

        .countdown-badge {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
            color: #38bdf8;
            background: rgba(56,189,248,0.1);
            padding: 4px 10px;
            border-radius: 6px;
            white-space: nowrap;
        }}

        .no-line-badge {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11px;
            color: #64748b;
            background: rgba(100,116,139,0.1);
            padding: 4px 10px;
            border-radius: 6px;
        }}

        .card-body {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-bottom: 14px;
        }}

        .stat {{
            display: flex;
            flex-direction: column;
            gap: 3px;
        }}

        .stat-label {{
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #475569;
        }}

        .stat-value {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 14px;
            font-weight: 500;
            color: #cbd5e1;
        }}

        .venue {{
            font-size: 11px;
            color: #475569;
            border-top: 1px solid #1e293b;
            padding-top: 10px;
        }}

        .live-card {{
            border-color: #f59e0b;
            background: rgba(245,158,11,0.03);
        }}

        .upcoming-card {{
            border-color: #1e3a5f;
        }}

        .no-line-card {{
            border-color: #1e293b;
            opacity: 0.7;
        }}

        .tomorrow-card {{
            border-color: #1e293b;
            background: #080c16;
        }}

        .live-indicator {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 10px;
            font-weight: 600;
            color: #f59e0b;
            text-transform: uppercase;
            letter-spacing: 2px;
            margin-bottom: 12px;
        }}

        .live-dot {{
            width: 6px;
            height: 6px;
            background: #f59e0b;
            border-radius: 50%;
            animation: pulse 1.5s infinite;
        }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; transform: scale(1); }}
            50% {{ opacity: 0.4; transform: scale(0.8); }}
        }}

        .history-day {{
            background: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
        }}

        .history-date {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
            color: #64748b;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 14px;
            padding-bottom: 10px;
            border-bottom: 1px solid #1e293b;
        }}

        .history-row {{
            display: grid;
            grid-template-columns: 2fr 1fr 1fr 80px;
            gap: 12px;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #0f1929;
        }}

        .history-row:last-child {{
            border-bottom: none;
        }}

        .history-game {{
            font-size: 13px;
            color: #cbd5e1;
        }}

        .history-score {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
            color: #64748b;
        }}

        .history-line {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
            color: #64748b;
        }}

        .history-result {{
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
            font-weight: 600;
            text-align: right;
        }}

        .footer {{
            text-align: center;
            padding: 24px;
            color: #334155;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 11px;
            border-top: 1px solid #1e293b;
            margin-top: 40px;
        }}

        .empty-state {{
            color: #334155;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 13px;
            padding: 20px;
            text-align: center;
        }}
    </style>
</head>
<body>

<div class="header">
    <div class="header-left">
        <h1>NBA Settlement System</h1>
        <p>Generated {data['generated_at']}</p>
    </div>
    <div class="header-right">
        <div class="stat-pill">
            <div class="number">{total_settled}</div>
            <div class="label">Settled</div>
        </div>
        <div class="stat-pill">
            <div class="number">{total_in_progress}</div>
            <div class="label">Live</div>
        </div>
        <div class="stat-pill">
            <div class="number">{total_upcoming}</div>
            <div class="label">Upcoming</div>
        </div>
        <div class="stat-pill">
            <div class="number">${total_volume:,}</div>
            <div class="label">Volume</div>
        </div>
    </div>
</div>

<div class="content">

    {"" if not data['settled'] else f'''
    <div class="section">
        <div class="section-header">
            <span class="section-title">✅ Settled Contracts</span>
            <span class="section-count">{len(data['settled'])}</span>
        </div>
        <div class="cards-grid">{settled_html}</div>
    </div>'''}

    {"" if not data['in_progress'] else f'''
    <div class="section">
        <div class="section-header">
            <span class="section-title">🔴 In Progress</span>
            <span class="section-count">{len(data['in_progress'])}</span>
        </div>
        <div class="cards-grid">{in_progress_html}</div>
    </div>'''}

    {"" if not data['upcoming'] else f'''
    <div class="section">
        <div class="section-header">
            <span class="section-title">⏰ Upcoming Contracts</span>
            <span class="section-count">{len(data['upcoming'])}</span>
        </div>
        <div class="cards-grid">{upcoming_html}</div>
    </div>'''}

    {"" if not data['no_line'] else f'''
    <div class="section">
        <div class="section-header">
            <span class="section-title">📊 Final Scores — No Line Available</span>
            <span class="section-count">{len(data['no_line'])}</span>
        </div>
        <div class="cards-grid">{no_line_html}</div>
    </div>'''}

    {"" if not data['tomorrow'] else f'''
    <div class="section">
        <div class="section-header">
            <span class="section-title">📅 Tomorrow's Games</span>
            <span class="section-count">{len(data['tomorrow'])}</span>
        </div>
        <div class="cards-grid">{tomorrow_html}</div>
    </div>'''}

    {"" if not data['history'] else f'''
    <div class="section">
        <div class="section-header">
            <span class="section-title">📜 Recent Settlements</span>
        </div>
        {history_html}
    </div>'''}

</div>

<div class="footer">
    NBA Settlement System — Mattingly Siegel — Built with Python, nba_api, The Odds API, TheSportsDB
</div>

</body>
</html>"""

    return html

# ============================================================
# MAIN — Generate and open dashboard
# ============================================================
print("Fetching live data...")
data = process_settlements()

print("Generating dashboard...")
html = generate_html(data)

with open("dashboard.html", "w") as f:
    f.write(html)

print("Opening dashboard in browser...")
webbrowser.open(f"file://{os.path.abspath('dashboard.html')}")
print("Done!")