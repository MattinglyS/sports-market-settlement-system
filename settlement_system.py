# ============================================================
# Automated Sports Market Settlement System
# Author: Mattingly Siegel
# Description: Demonstrates an automated settlement workflow.
# Connects to TheSportsDB API for live NBA team data, matches
# teams against predefined contract thresholds, settles each
# contract as YES/NO/PUSH, logs all decisions for CFTC 
# compliance, and flags incomplete contracts for manual review.
# Note: Game scores are simulated for demonstration purposes.
# In production, scores would be pulled from a live data feed.
# ============================================================

import requests
import datetime
import pandas as pd

# ============================================================
# SECTION 1: CONTRACT DEFINITIONS
# Pre-defined prediction market contracts with thresholds.
# In production, these would be loaded from a database.
# ============================================================
contracts = {
    "Boston Celtics": {"threshold": 110, "sport": "NBA"},
    "Brooklyn Nets": {"threshold": 105, "sport": "NBA"},
    "Chicago Bulls": {"threshold": 108, "sport": "NBA"},
    "Atlanta Hawks": {"threshold": 100, "sport": "NBA"},
    "Charlotte Hornets": {"threshold": 95, "sport": "NBA"},
}

# ============================================================
# SECTION 2: GAME RESULTS
# Simulated game results for demonstration purposes.
# In production, these would come from a live data feed.
# ============================================================
game_results = {
    "Boston Celtics": 112,
    "Brooklyn Nets": "TBD",
    "Chicago Bulls": 108,
    "Atlanta Hawks": 99,
    "Charlotte Hornets": 101,
}

# ============================================================
# SECTION 3: SETTLEMENT FUNCTION
# Core settlement engine. Compares score against threshold,
# returns YES/NO/PUSH, logs every decision with timestamp
# for CFTC compliance and audit trail purposes.
# ============================================================
def settle_contract(team, score, threshold, stadium, location):
    timestamp = datetime.datetime.now()

    try:
        score = int(score)

        if score > threshold:
            result = "YES"
        elif score == threshold:
            result = "PUSH"
        else:
            result = "NO"

    except ValueError:
        # Handles missing or invalid score data gracefully
        # flags the contract for review without crashing the settlement run
        result = "ERROR - Needs manual review"

    # Build formatted log entry using f-string
    log_entry = f"{timestamp} | {team} | {stadium} | {location} | Score: {score} | Threshold: {threshold} | Result: {result}"

    # Print to console for real-time monitoring
    print(log_entry)

    # Append to permanent log file for audit trail
    with open("capstone_log.txt", "a") as log_file:
        log_file.write(log_entry + "\n")

    return result

# ============================================================
# SECTION 4: API CALL
# Pulls live NBA team data from TheSportsDB API.
# Returns a dictionary of team info for use in settlement output.
# ============================================================
def get_nba_teams():
    try:
        response = requests.get(
            "https://www.thesportsdb.com/api/v1/json/3/search_all_teams.php?l=NBA"
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
        print("WARNING: Could not reach API. Proceeding with local data.")
        return {}

# ============================================================
# SECTION 5: MAIN SETTLEMENT LOOP
# Pulls live team data from API, loops through all contracts,
# matches game results, and runs each through the settlement engine.
# ============================================================
print("--- SETTLEMENT SYSTEM STARTING ---")
print(f"Time: {datetime.datetime.now()}")
print("----------------------------------")

# Pull live NBA teams from API
nba_teams = get_nba_teams()

results = []

for team, contract in contracts.items():
    threshold = contract["threshold"]
    sport = contract["sport"]

    # Pull stadium and location from live API data
    if nba_teams and team in nba_teams:
        stadium = nba_teams[team]["stadium"]
        location = nba_teams[team]["location"]
    else:
        stadium = "Unknown"
        location = "Unknown"
        print(f"WARNING: {team} not found in live API data")

    # Get score from game results
    if team in game_results:
        score = game_results[team]
    else:
        score = "TBD"

    # Run settlement and collect result
    result = settle_contract(team, score, threshold, stadium, location)
    results.append({
        "team": team,
        "stadium": stadium,
        "location": location,
        "score": score,
        "threshold": threshold,
        "result": result,
        "sport": sport
    })

print("----------------------------------")
print("--- SETTLEMENT COMPLETE ---")

# ============================================================
# SECTION 6: PANDAS ANALYSIS & REPORTING
# Analyzes settlement results, generates summary,
# and exports any flagged contracts to a CSV
# for supervisor review.
# ============================================================
df = pd.DataFrame(results)

print("\n--- RESULT SUMMARY ---")
print(df["result"].value_counts())

# Filter flagged contracts that need manual review
errors = df[df["result"] == "ERROR - Needs manual review"]

if len(errors) > 0:
    errors.to_csv("manual_review.csv", index=False)
    print(f"\n⚠️  {len(errors)} contract(s) need manual review - saved to manual_review.csv")
else:
    print("\n✅ All contracts settled successfully!")
