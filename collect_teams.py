"""
collect_teams.py
Fetches recent form (last 5 results) for all 48 WC 2026 teams
using Free API Live Football Data on RapidAPI.
Updates teams.json with form data.
Run by GitHub Actions weekly.
"""

import requests, json, os, time
from datetime import datetime, timezone

API_KEY = os.environ.get("RAPIDAPI_KEY", "")
HOST    = "free-api-live-football-data.p.rapidapi.com"
BASE    = f"https://{HOST}"
HEADERS = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": HOST}

TEAM_SEARCH_NAMES = {
    "Argentina":"Argentina","France":"France","England":"England",
    "Spain":"Spain","Brazil":"Brazil","Portugal":"Portugal",
    "Belgium":"Belgium","Netherlands":"Netherlands","Germany":"Germany",
    "Morocco":"Morocco","USA":"United States","Uruguay":"Uruguay",
    "Colombia":"Colombia","Japan":"Japan","Croatia":"Croatia",
    "Senegal":"Senegal","Switzerland":"Switzerland","Mexico":"Mexico",
    "Ecuador":"Ecuador","South Korea":"South Korea","Norway":"Norway",
    "Australia":"Australia","Tunisia":"Tunisia","Algeria":"Algeria",
    "Sweden":"Sweden","Canada":"Canada","Iran":"Iran","Czechia":"Czech Republic",
    "Scotland":"Scotland","Ivory Coast":"Ivory Coast","Ghana":"Ghana",
    "Austria":"Austria","Paraguay":"Paraguay","South Africa":"South Africa",
    "New Zealand":"New Zealand","Iraq":"Iraq","Cape Verde":"Cape Verde",
    "Türkiye":"Turkey","Bosnia":"Bosnia","Saudi Arabia":"Saudi Arabia",
    "Egypt":"Egypt","Qatar":"Qatar","Uzbekistan":"Uzbekistan",
    "DR Congo":"DR Congo","Panama":"Panama","Jordan":"Jordan",
    "Haiti":"Haiti","Curaçao":"Curacao"
}

def get_team_id(name):
    try:
        r = requests.get(f"{BASE}/football-get-all-teams",
                         headers=HEADERS,
                         params={"name": name},
                         timeout=10)
        r.raise_for_status()
        data = r.json()
        teams = data.get("response", [])
        for t in teams:
            team = t.get("team", {})
            if name.lower() in team.get("name", "").lower():
                return team.get("id")
        return None
    except Exception as e:
        print(f"  ⚠️  Team ID lookup failed for {name}: {e}")
        return None

def get_recent_form(team_id):
    try:
        r = requests.get(f"{BASE}/football-get-all-fixtures",
                         headers=HEADERS,
                         params={"team": team_id, "last": 5},
                         timeout=10)
        r.raise_for_status()
        data  = r.json()
        fixtures = data.get("response", [])
        form = []
        for fix in fixtures:
            teams  = fix.get("teams", {})
            goals  = fix.get("goals", {})
            home   = teams.get("home", {})
            away   = teams.get("away", {})
            hg     = goals.get("home", 0) or 0
            ag     = goals.get("away", 0) or 0
            is_home = home.get("id") == team_id
            if is_home:
                result = "W" if hg > ag else ("D" if hg == ag else "L")
                score  = f"{hg}-{ag}"
                opp    = away.get("name", "?")
            else:
                result = "W" if ag > hg else ("D" if hg == ag else "L")
                score  = f"{ag}-{hg}"
                opp    = home.get("name", "?")
            form.append({"result": result, "score": score, "opponent": opp})
        return form
    except Exception as e:
        print(f"  ⚠️  Form fetch failed: {e}")
        return []

def main():
    if not API_KEY:
        print("❌ RAPIDAPI_KEY not set. Skipping.")
        return

    with open("teams.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    teams = data["teams"]
    updated = 0

    for team_name, search_name in TEAM_SEARCH_NAMES.items():
        if team_name not in teams:
            continue
        print(f"📡 {team_name}…", end=" ", flush=True)
        tid = get_team_id(search_name)
        if tid:
            form = get_recent_form(tid)
            teams[team_name]["recent_form"] = form
            print(f"✅ Form: {[f['result'] for f in form]}")
            updated += 1
        else:
            print("⚠️  Not found")
        time.sleep(0.5)  # be nice to the API

    data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open("teams.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Updated form for {updated} teams")

if __name__ == "__main__":
    main()
