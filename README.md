# NBA Settlement System
### Author: Mattingly Siegel

A live automated settlement system that pulls real data from three APIs to track, grade, and report NBA prediction market contracts in real time.

## Live Dashboard
👉 [View Live Dashboard](https://mattinglys.github.io/sports-market-settlement-system/dashboard.html)

## How To Run

**Step 1 — Install required libraries (first time only):**

pip install requests pandas pytz nba_api

**Step 2 — Run the settlement system:**

python settlement_system.py

**Step 3 — Generate an updated live dashboard:**

python generate_dashboard.py

The system automatically pulls today's games, lines, and live scores. No configuration needed. Results update every time you run it.

## Data Sources
- **The Odds API** — real consensus over/under lines from major bookmakers
- **nba_api** — real live and final NBA scores
- **TheSportsDB** — venue and location data for every team

## Files
- `settlement_system.py` — main settlement engine
- `db.py` — database module for storing contract lines
- `generate_dashboard.py` — generates the live HTML dashboard
- `dashboard.html` — sample dashboard output

## Background
Built as preparation for a role in prediction market operations. Designed to mirror real settlement workflows in a CFTC-regulated exchange environment.
