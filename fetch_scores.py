"""
fetch_scores.py
Fetches FIFA World Cup 2026 match results from football-data.org
and updates data.json for the GitHub Pages site.

Run by GitHub Actions every 30 minutes during the tournament.
Requires: FOOTBALL_API_KEY environment variable (store as GitHub Secret)
"""

import requests
import json
import os
import sys
from datetime import datetime, timezone

API_KEY  = os.environ.get("FOOTBALL_API_KEY", "")
BASE_URL = "https://api.football-data.org/v4"
HEADERS  = {"X-Auth-Token": API_KEY}
DATA_FILE = "data.json"

# ── Name normalisation ─────────────────────────────────────────
# Maps football-data.org team names → our display names
NAME_MAP = {
    "United States": "USA",
    "Turkey": "Türkiye",
    "Côte d'Ivoire": "Ivory Coast",
    "Bosnia and Herzegovina": "Bosnia",
    "Congo DR": "DR Congo",
    "Czech Republic": "Czechia",
    "Korea Republic": "South Korea",
}

FLAG_MAP = {
    "Mexico":"🇲🇽","South Africa":"🇿🇦","South Korea":"🇰🇷","Czechia":"🇨🇿",
    "Canada":"🇨🇦","Qatar":"🇶🇦","Switzerland":"🇨🇭","Bosnia":"🇧🇦",
    "Brazil":"🇧🇷","Morocco":"🇲🇦","Scotland":"🏴󠁧󠁢󠁳󠁣󠁴󠁿","Haiti":"🇭🇹",
    "USA":"🇺🇸","Paraguay":"🇵🇾","Australia":"🇦🇺","Türkiye":"🇹🇷",
    "Germany":"🇩🇪","Ivory Coast":"🇨🇮","Ecuador":"🇪🇨","Curaçao":"🇨🇼",
    "Netherlands":"🇳🇱","Japan":"🇯🇵","Sweden":"🇸🇪","Tunisia":"🇹🇳",
    "Belgium":"🇧🇪","Egypt":"🇪🇬","Iran":"🇮🇷","New Zealand":"🇳🇿",
    "Spain":"🇪🇸","Saudi Arabia":"🇸🇦","Uruguay":"🇺🇾","Cape Verde":"🇨🇻",
    "France":"🇫🇷","Senegal":"🇸🇳","Norway":"🇳🇴","Iraq":"🇮🇶",
    "Argentina":"🇦🇷","Algeria":"🇩🇿","Austria":"🇦🇹","Jordan":"🇯🇴",
    "Portugal":"🇵🇹","DR Congo":"🇨🇩","Uzbekistan":"🇺🇿","Colombia":"🇨🇴",
    "England":"🏴󠁧󠁢󠁥󠁮󠁧󠁿","Croatia":"🇭🇷","Ghana":"🇬🇭","Panama":"🇵🇦",
    "TBD":"🏳",
}

STAGE_MAP = {
    "GROUP_STAGE": "group",
    "LAST_32": "r32",
    "LAST_16": "r16",
    "QUARTER_FINALS": "qf",
    "SEMI_FINALS": "sf",
    "THIRD_PLACE": "bronze",
    "FINAL": "final",
}

def normalise(name):
    return NAME_MAP.get(name, name)

def flag(name):
    return FLAG_MAP.get(name, "🏳")

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    data["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ data.json saved at {data['last_updated']}")

def fetch_matches():
    url = f"{BASE_URL}/competitions/WC/matches?season=2026"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json().get("matches", [])
    except Exception as e:
        print(f"⚠️  Matches fetch failed: {e}")
        return []

def fetch_scorers(match_id):
    """Fetch goal scorers for a specific match."""
    url = f"{BASE_URL}/matches/{match_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        goals = data.get("goals", [])
        scorers = []
        for g in goals:
            scorer = g.get("scorer", {}).get("name", "Unknown")
            team   = normalise(g.get("team", {}).get("name", ""))
            minute = g.get("minute", "?")
            scorers.append({"name": scorer, "team": team, "minute": minute})
        return scorers
    except Exception as e:
        print(f"  ⚠️  Scorers fetch failed for match {match_id}: {e}")
        return []

def build_standings(matches):
    """Compute group standings from finished group stage matches."""
    groups = {}
    team_flags = {}

    for m in matches:
        if m["stage"] != "group" or m["status"] != "FINISHED":
            continue
        grp = m["group"]
        if grp not in groups:
            groups[grp] = {}

        for side, opp in [("home", "away"), ("away", "home")]:
            team = m[f"{side}"]
            opp_team = m[f"{opp}"]
            gs = m[f"{side}_score"] or 0
            ga = m[f"{opp}_score"] or 0
            team_flags[team] = m[f"{side}_flag"]

            if team not in groups[grp]:
                groups[grp][team] = {"p":0,"w":0,"d":0,"l":0,"gf":0,"ga":0,"gd":0,"pts":0}
            t = groups[grp][team]
            t["p"]  += 1
            t["gf"] += gs
            t["ga"] += ga
            t["gd"]  = t["gf"] - t["ga"]
            if gs > ga:
                t["w"]   += 1
                t["pts"] += 3
            elif gs == ga:
                t["d"]   += 1
                t["pts"] += 1
            else:
                t["l"]   += 1

    standings = {}
    for grp, teams in groups.items():
        table = []
        for team, stats in teams.items():
            table.append({
                "team": team,
                "flag": team_flags.get(team, "🏳"),
                **stats
            })
        # Sort: pts desc, gd desc, gf desc
        table.sort(key=lambda x: (-x["pts"], -x["gd"], -x["gf"]))
        standings[grp] = table

    return standings

def merge_matches(existing_matches, api_matches):
    """Merge API data into our existing match list."""
    # Build lookup from our data by UTC time + home team
    our_map = {}
    for m in existing_matches:
        key = (m["utc"][:16], m["home"])
        our_map[key] = m

    for api_m in api_matches:
        utc_raw = api_m.get("utcDate", "")
        utc     = utc_raw[:16] if utc_raw else ""
        home    = normalise(api_m.get("homeTeam", {}).get("name", "TBD"))
        away    = normalise(api_m.get("awayTeam", {}).get("name", "TBD"))
        status  = api_m.get("status", "SCHEDULED")
        score   = api_m.get("score", {})
        full    = score.get("fullTime", {})
        hs      = full.get("home")
        as_     = full.get("away")
        stage   = STAGE_MAP.get(api_m.get("stage", ""), "group")
        api_id  = api_m.get("id")

        key = (utc, home)
        if key in our_map:
            m = our_map[key]
            m["home"]       = home
            m["away"]       = away
            m["home_flag"]  = flag(home)
            m["away_flag"]  = flag(away)
            m["status"]     = status
            m["home_score"] = hs
            m["away_score"] = as_
            if status == "FINISHED" and not m.get("scorers") and api_id:
                print(f"  Fetching scorers for {home} vs {away}…")
                m["scorers"] = fetch_scorers(api_id)
        else:
            # Knockout match we don't have yet — add it
            if stage != "group":
                existing_matches.append({
                    "id": api_id,
                    "utc": utc_raw,
                    "home": home, "home_flag": flag(home),
                    "away": away, "away_flag": flag(away),
                    "group": None, "stage": stage,
                    "status": status,
                    "home_score": hs, "away_score": as_,
                    "scorers": []
                })

    return existing_matches

def main():
    if not API_KEY:
        print("❌ FOOTBALL_API_KEY not set. Skipping fetch.")
        sys.exit(0)

    print("📡 Fetching match data from football-data.org…")
    api_matches = fetch_matches()

    if not api_matches:
        print("⚠️  No match data returned. Keeping existing data.json unchanged.")
        sys.exit(0)

    print(f"✅ Got {len(api_matches)} matches from API")

    data = load_data()
    data["matches"] = merge_matches(data["matches"], api_matches)
    data["standings"] = build_standings(data["matches"])

    # Check for a winner
    final = next((m for m in data["matches"] if m["stage"] == "final" and m["status"] == "FINISHED"), None)
    if final:
        if (final["home_score"] or 0) > (final["away_score"] or 0):
            data["winner"] = {"team": final["home"], "flag": final["home_flag"]}
        elif (final["away_score"] or 0) > (final["home_score"] or 0):
            data["winner"] = {"team": final["away"], "flag": final["away_flag"]}

    save_data(data)

if __name__ == "__main__":
    main()
