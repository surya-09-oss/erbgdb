"""Cricbuzz scraper - scrapes live cricket data from Cricbuzz.com.

Cricbuzz migrated to a Next.js / React Server Components architecture.
Match data is now embedded in RSC script payloads as JSON objects, which
is far more reliable than scraping HTML class names.
"""

import json
import random
import re

import httpx
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

BASE_URL = "https://www.cricbuzz.com"


def _get_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Cache-Control": "no-cache",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }


def _extract_json_object(text: str, start: int) -> dict | None:
    """Extract a complete JSON object starting at *start* (must point to '{')."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _extract_rsc_payloads(page_text: str) -> list[str]:
    """Extract and unescape all RSC script payloads from the page."""
    raw = re.findall(
        r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', page_text
    )
    results = []
    for payload in raw:
        try:
            results.append(payload.encode().decode("unicode_escape"))
        except (UnicodeDecodeError, ValueError):
            continue
    return results


def _extract_miniscore(page_text: str) -> dict | None:
    """Extract the ``miniscore`` JSON object from Cricbuzz RSC script payloads."""
    for unescaped in _extract_rsc_payloads(page_text):
        if "miniscore" not in unescaped:
            continue
        ms_match = re.search(r'"miniscore"\s*:\s*\{', unescaped)
        if not ms_match:
            continue
        obj = _extract_json_object(unescaped, ms_match.end() - 1)
        if obj:
            return obj
    return None


def _extract_match_list(page_text: str) -> list[dict]:
    """Extract matchInfo + matchScore pairs from the live-scores RSC payloads.

    Returns a list of dicts, each with ``matchInfo`` and optionally ``matchScore``.
    """
    matches: list[dict] = []
    seen_ids: set[int] = set()

    for unescaped in _extract_rsc_payloads(page_text):
        if "matchInfo" not in unescaped:
            continue
        for m in re.finditer(r'"matchInfo"\s*:\s*\{', unescaped):
            info_obj = _extract_json_object(unescaped, m.end() - 1)
            if not info_obj:
                continue
            mid = info_obj.get("matchId")
            if mid is None or mid in seen_ids:
                continue
            seen_ids.add(mid)

            entry: dict = {"matchInfo": info_obj}

            # Look for matchScore right after matchInfo
            after_info = unescaped[m.end() - 1:]
            depth = 0
            end_pos = 0
            for j, c in enumerate(after_info):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        end_pos = j + 1
                        break

            remainder = after_info[end_pos:]
            score_m = re.search(r'"matchScore"\s*:\s*\{', remainder[:200])
            if score_m:
                score_obj = _extract_json_object(remainder, score_m.end() - 1)
                if score_obj:
                    entry["matchScore"] = score_obj

            matches.append(entry)

    return matches


def _format_innings_score(team_name: str, innings: dict) -> str:
    """Format an innings score like 'IND 164/5 (20)'."""
    runs = innings.get("runs", "")
    wkts = innings.get("wickets")
    overs = innings.get("overs", "")
    score_str = str(runs)
    if wkts is not None:
        score_str += f"/{wkts}"
    return f"{team_name} {score_str} ({overs})"


async def fetch_live_matches() -> list[dict]:
    """Fetch all current live cricket matches from Cricbuzz."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(
                f"{BASE_URL}/cricket-match/live-scores", headers=_get_headers()
            )
            r.raise_for_status()
        except httpx.HTTPError:
            return []

    match_list = _extract_match_list(r.text)
    results = []

    for entry in match_list:
        info = entry["matchInfo"]
        score_data = entry.get("matchScore", {})

        match_id = str(info.get("matchId", ""))
        series = info.get("seriesName", "")
        match_desc = info.get("matchDesc", "")
        title = f"{series}, {match_desc}" if series and match_desc else series or match_desc

        team1 = info.get("team1", {})
        team2 = info.get("team2", {})
        status = info.get("status", "Unknown")
        state = info.get("state", "")

        teams = []
        t1_score = score_data.get("team1Score", {})
        t2_score = score_data.get("team2Score", {})

        t1_name = team1.get("teamSName") or team1.get("teamName", "")
        t2_name = team2.get("teamSName") or team2.get("teamName", "")

        t1_inngs = t1_score.get("inngs1", {})
        if t1_inngs:
            teams.append({
                "name": t1_name,
                "score": _format_innings_score(t1_name, t1_inngs),
            })
        else:
            teams.append({"name": t1_name, "score": None})

        t2_inngs = t2_score.get("inngs1", {})
        if t2_inngs:
            teams.append({
                "name": t2_name,
                "score": _format_innings_score(t2_name, t2_inngs),
            })
        else:
            teams.append({"name": t2_name, "score": None})

        results.append({
            "match_id": match_id,
            "title": title,
            "status": status,
            "state": state,
            "teams": teams,
        })

    return results


async def fetch_match_score(match_id: str) -> dict:
    """Fetch detailed live score for a specific match from Cricbuzz."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(
                f"{BASE_URL}/live-cricket-scores/{match_id}",
                headers=_get_headers(),
            )
            r.raise_for_status()
        except httpx.HTTPError:
            return {"error": "Failed to fetch match data", "match_id": match_id}

    page_text = r.text
    soup = BeautifulSoup(r.content, "html.parser")

    # --- title ---
    h1 = soup.find("h1")
    title = None
    if h1:
        title = h1.text.strip()
        for suffix in [" - Commentary", ", Commentary"]:
            if title.endswith(suffix):
                title = title[: -len(suffix)]

    # --- miniscore ---
    ms = _extract_miniscore(page_text)

    if ms is None:
        return {
            "match_id": match_id,
            "title": title,
            "status": "Match Stats will Update Soon",
            "status_type": "upcoming",
            "live_score": None,
            "run_rate": None,
            "match_date": None,
            "batters": [],
            "bowlers": [],
        }

    # --- status ---
    msd = ms.get("matchScoreDetails", {})
    status_text = msd.get("customStatus") or ms.get("status") or "Match Stats will Update Soon"
    state = msd.get("state", "")

    status_type_map = {
        "Complete": "completed",
        "In Progress": "in_progress",
        "Preview": "upcoming",
        "Abandoned": "abandoned",
        "Stumps": "stumps",
    }
    status_type = status_type_map.get(state, "in_progress" if state else "upcoming")

    # --- live score ---
    bat_team = ms.get("batTeam", {})
    team_name = (
        ms.get("batTeamScoreObj", {}).get("teamName")
        or bat_team.get("teamName")
        or bat_team.get("teamId", "")
    )
    team_score = bat_team.get("teamScore", "")
    team_wkts = bat_team.get("teamWkts")
    overs = ms.get("overs", "")

    live_score = None
    if team_score != "" or team_wkts is not None:
        score_str = str(team_score)
        if team_wkts is not None:
            score_str += f"/{team_wkts}"
        live_score = f"{team_name} {score_str} ({overs})"

    # --- run rate ---
    crr = ms.get("currentRunRate")
    run_rate = str(crr) if crr else None

    # --- batters ---
    batters = []
    for key in ("batsmanStriker", "batsmanNonStriker"):
        player = ms.get(key, {})
        if player.get("id", 0) == 0 and not player.get("name"):
            continue
        batters.append({
            "name": player.get("name", ""),
            "runs": str(player.get("runs", 0)),
            "balls": str(player.get("balls", 0)),
            "strike_rate": str(player.get("strikeRate", "0.00")),
        })

    # --- bowlers ---
    bowlers = []
    for key in ("bowlerStriker", "bowlerNonStriker"):
        player = ms.get(key, {})
        if player.get("id", 0) == 0 and not player.get("name"):
            continue
        bowlers.append({
            "name": player.get("name", ""),
            "overs": str(player.get("overs", 0)),
            "runs_conceded": str(player.get("runs", 0)),
            "wickets": str(player.get("wickets", 0)),
            "economy": str(player.get("economy", "0.00")),
        })

    return {
        "match_id": match_id,
        "title": title,
        "status": status_text,
        "status_type": status_type,
        "live_score": live_score,
        "run_rate": run_rate,
        "match_date": None,
        "batters": batters,
        "bowlers": bowlers,
    }
