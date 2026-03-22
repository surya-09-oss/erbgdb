"""Cricket API scraper - compatible with sanwebinfo/cricket-api JSON format.

Scrapes live cricket data from Cricbuzz.com and returns it in the same
JSON structure used by https://github.com/sanwebinfo/cricket-api.

Cricbuzz migrated to a Next.js / React Server Components architecture.
Match data is now embedded in the page as a ``miniscore`` JSON object
inside RSC script payloads, which is far more reliable than scraping
HTML class names.
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

NOT_FOUND = "Data Not Found"
UPDATING = "Match Stats will Update Soon"


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


def _extract_miniscore(page_text: str) -> dict | None:
    """Extract the ``miniscore`` JSON object from Cricbuzz RSC script payloads."""
    rsc_payloads = re.findall(
        r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', page_text
    )
    for payload in rsc_payloads:
        if "miniscore" not in payload:
            continue
        try:
            unescaped = payload.encode().decode("unicode_escape")
        except (UnicodeDecodeError, ValueError):
            continue
        ms_match = re.search(r'"miniscore"\s*:\s*\{', unescaped)
        if not ms_match:
            continue
        obj = _extract_json_object(unescaped, ms_match.end() - 1)
        if obj:
            return obj
    return None


def _extract_title(soup: BeautifulSoup) -> str:
    """Extract match title from the page ``<h1>`` element."""
    h1 = soup.find("h1")
    if h1:
        title = h1.text.strip()
        for suffix in [" - Commentary", ", Commentary"]:
            if title.endswith(suffix):
                title = title[: -len(suffix)]
        return title
    return NOT_FOUND


def _format_live_score(miniscore: dict) -> str:
    """Build a live-score string like ``IND 144/3 (15)`` from miniscore data."""
    bat_team = miniscore.get("batTeam", {})
    # teamName is in batTeamScoreObj, not batTeam
    team_name = (
        miniscore.get("batTeamScoreObj", {}).get("teamName")
        or bat_team.get("teamName")
        or bat_team.get("teamId", "")
    )
    score = bat_team.get("teamScore", "")
    wkts = bat_team.get("teamWkts")
    overs = miniscore.get("overs", "")

    if score == "" and wkts is None:
        return NOT_FOUND

    score_str = str(score)
    if wkts is not None:
        score_str += f"/{wkts}"

    return f"{team_name} {score_str} ({overs})"


def _safe(value: object, fallback: str = UPDATING) -> str:
    """Return *value* as a string, falling back if empty/zero/None."""
    if value is None or value == "":
        return fallback
    return str(value)


def _is_player_empty(player: dict) -> bool:
    """Return True if the player object has no real data (id == 0, empty name)."""
    return player.get("id", 0) == 0 and not player.get("name")


async def fetch_score_flat(match_id: str) -> dict:
    """Fetch match score in the flat JSON format used by /score endpoint.

    Returns the same JSON structure as sanwebinfo/cricket-api ``/score`` route.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(
                f"{BASE_URL}/live-cricket-scores/{match_id}",
                headers=_get_headers(),
            )
            r.raise_for_status()
        except httpx.HTTPError:
            return _not_found_flat()

    page_text = r.text
    soup = BeautifulSoup(r.content, "html.parser")

    # --- title from <h1> ---
    title = _extract_title(soup)

    # --- miniscore from RSC payload ---
    ms = _extract_miniscore(page_text)

    if ms is None:
        # Fallback: try to get status from HTML
        status_div = soup.find("div", attrs={"class": "text-cbTextLink"})
        status = status_div.text.strip() if status_div else "Match Stats will Update Soon..."
        return {
            "title": title,
            "update": status,
            "livescore": NOT_FOUND,
            "runrate": "CRR: " + NOT_FOUND,
            "batterone": UPDATING,
            "batsmanonerun": UPDATING,
            "batsmanoneball": "(" + UPDATING + ")",
            "batsmanonesr": UPDATING,
            "battertwo": UPDATING,
            "batsmantworun": UPDATING,
            "batsmantwoball": "(" + UPDATING + ")",
            "batsmantwosr": UPDATING,
            "bowlerone": UPDATING,
            "bowleroneover": UPDATING,
            "bowleronerun": UPDATING,
            "bowleronewickers": UPDATING,
            "bowleroneeconomy": UPDATING,
            "bowlertwo": UPDATING,
            "bowlertwoover": UPDATING,
            "bowlertworun": UPDATING,
            "bowlertwowickers": UPDATING,
            "bowlertwoeconomy": UPDATING,
        }

    # --- status ---
    msd = ms.get("matchScoreDetails", {})
    status = msd.get("customStatus") or ms.get("status") or "Match Stats will Update Soon..."

    # --- live score ---
    live_score = _format_live_score(ms)

    # --- run rate ---
    crr = ms.get("currentRunRate")
    run_rate = str(crr) if crr else NOT_FOUND

    # --- batters ---
    striker = ms.get("batsmanStriker", {})
    non_striker = ms.get("batsmanNonStriker", {})

    if _is_player_empty(striker):
        batter_one = UPDATING
        batter_one_run = UPDATING
        batter_one_ball = UPDATING
        batter_one_sr = UPDATING
    else:
        batter_one = _safe(striker.get("name"))
        batter_one_run = _safe(striker.get("runs"))
        batter_one_ball = _safe(striker.get("balls"))
        batter_one_sr = _safe(striker.get("strikeRate"))

    if _is_player_empty(non_striker):
        batter_two = UPDATING
        batter_two_run = UPDATING
        batter_two_ball = UPDATING
        batter_two_sr = UPDATING
    else:
        batter_two = _safe(non_striker.get("name"))
        batter_two_run = _safe(non_striker.get("runs"))
        batter_two_ball = _safe(non_striker.get("balls"))
        batter_two_sr = _safe(non_striker.get("strikeRate"))

    # --- bowlers ---
    bowler_s = ms.get("bowlerStriker", {})
    bowler_ns = ms.get("bowlerNonStriker", {})

    if _is_player_empty(bowler_s):
        bowler_one = UPDATING
        bowler_one_over = UPDATING
        bowler_one_run = UPDATING
        bowler_one_wicket = UPDATING
        bowler_one_eco = UPDATING
    else:
        bowler_one = _safe(bowler_s.get("name"))
        bowler_one_over = _safe(bowler_s.get("overs"))
        bowler_one_run = _safe(bowler_s.get("runs"))
        bowler_one_wicket = _safe(bowler_s.get("wickets"))
        bowler_one_eco = _safe(bowler_s.get("economy"))

    if _is_player_empty(bowler_ns):
        bowler_two = UPDATING
        bowler_two_over = UPDATING
        bowler_two_run = UPDATING
        bowler_two_wicket = UPDATING
        bowler_two_eco = UPDATING
    else:
        bowler_two = _safe(bowler_ns.get("name"))
        bowler_two_over = _safe(bowler_ns.get("overs"))
        bowler_two_run = _safe(bowler_ns.get("runs"))
        bowler_two_wicket = _safe(bowler_ns.get("wickets"))
        bowler_two_eco = _safe(bowler_ns.get("economy"))

    return {
        "title": title,
        "update": status,
        "livescore": live_score,
        "runrate": "CRR: " + run_rate,
        "batterone": batter_one,
        "batsmanonerun": batter_one_run,
        "batsmanoneball": "(" + batter_one_ball + ")",
        "batsmanonesr": batter_one_sr,
        "battertwo": batter_two,
        "batsmantworun": batter_two_run,
        "batsmantwoball": "(" + batter_two_ball + ")",
        "batsmantwosr": batter_two_sr,
        "bowlerone": bowler_one,
        "bowleroneover": bowler_one_over,
        "bowleronerun": bowler_one_run,
        "bowleronewickers": bowler_one_wicket,
        "bowleroneeconomy": bowler_one_eco,
        "bowlertwo": bowler_two,
        "bowlertwoover": bowler_two_over,
        "bowlertworun": bowler_two_run,
        "bowlertwowickers": bowler_two_wicket,
        "bowlertwoeconomy": bowler_two_eco,
    }


async def fetch_score_live(match_id: str) -> dict:
    """Fetch match score in the nested JSON format used by /score/live endpoint.

    Returns the same JSON structure as sanwebinfo/cricket-api ``/score/live`` route.
    """
    flat = await fetch_score_flat(match_id)
    return {
        "success": "true",
        "livescore": {
            "title": flat["title"],
            "update": flat["update"],
            "current": flat["livescore"],
            "runrate": flat["runrate"],
            "batsman": flat["batterone"],
            "batsmanrun": flat["batsmanonerun"],
            "ballsfaced": flat["batsmanoneball"],
            "sr": flat["batsmanonesr"],
            "batsmantwo": flat["battertwo"],
            "batsmantworun": flat["batsmantworun"],
            "batsmantwoballfaced": flat["batsmantwoball"],
            "batsmantwosr": flat["batsmantwosr"],
            "bowler": flat["bowlerone"],
            "bowlerover": flat["bowleroneover"],
            "bowlerruns": flat["bowleronerun"],
            "bowlerwickets": flat["bowleronewickers"],
            "bowlereconomy": flat["bowleroneeconomy"],
            "bowlertwo": flat["bowlertwo"],
            "bowlertwoover": flat["bowlertwoover"],
            "bowlertworuns": flat["bowlertworun"],
            "bowlertwowickets": flat["bowlertwowickers"],
            "bowlertwoeconomy": flat["bowlertwoeconomy"],
        },
    }


def _not_found_flat() -> dict:
    return {
        "title": NOT_FOUND,
        "update": NOT_FOUND,
        "livescore": NOT_FOUND,
        "runrate": NOT_FOUND,
        "batterone": NOT_FOUND,
        "batsmanonerun": NOT_FOUND,
        "batsmanoneball": NOT_FOUND,
        "batsmanonesr": NOT_FOUND,
        "battertwo": NOT_FOUND,
        "batsmantworun": NOT_FOUND,
        "batsmantwoball": NOT_FOUND,
        "batsmantwosr": NOT_FOUND,
        "bowlerone": NOT_FOUND,
        "bowleroneover": NOT_FOUND,
        "bowleronerun": NOT_FOUND,
        "bowleronewickers": NOT_FOUND,
        "bowleroneeconomy": NOT_FOUND,
        "bowlertwo": NOT_FOUND,
        "bowlertwoover": NOT_FOUND,
        "bowlertworun": NOT_FOUND,
        "bowlertwowickers": NOT_FOUND,
        "bowlertwoeconomy": NOT_FOUND,
    }


def _not_found_live() -> dict:
    return {
        "success": "true",
        "livescore": {
            "title": NOT_FOUND,
            "update": NOT_FOUND,
            "current": NOT_FOUND,
            "runrate": NOT_FOUND,
            "batsman": NOT_FOUND,
            "batsmanrun": NOT_FOUND,
            "ballsfaced": NOT_FOUND,
            "sr": NOT_FOUND,
            "batsmantwo": NOT_FOUND,
            "batsmantworun": NOT_FOUND,
            "batsmantwoballfaced": NOT_FOUND,
            "batsmantwosr": NOT_FOUND,
            "bowler": NOT_FOUND,
            "bowlerover": NOT_FOUND,
            "bowlerruns": NOT_FOUND,
            "bowlerwickets": NOT_FOUND,
            "bowlereconomy": NOT_FOUND,
            "bowlertwo": NOT_FOUND,
            "bowlertwoover": NOT_FOUND,
            "bowlertworuns": NOT_FOUND,
            "bowlertwowickets": NOT_FOUND,
            "bowlertwoeconomy": NOT_FOUND,
        },
    }
