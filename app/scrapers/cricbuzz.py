"""Cricbuzz scraper - scrapes live cricket data from Cricbuzz.com."""

import json
import random
import re

import httpx
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

BASE_URL = "https://www.cricbuzz.com"

# Match states from Cricbuzz
LIVE_STATES = {"In Progress", "Toss", "Stumps", "Lunch", "Tea", "Innings Break", "Drink"}
COMPLETED_STATES = {"Complete", "Abandoned", "No Result"}
UPCOMING_STATES = {"Preview", "Upcoming"}


def _get_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Cache-Control": "no-cache",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }


def _safe_text(soup: BeautifulSoup, selector: str, class_name: str, index: int = 0) -> str | None:
    elements = soup.find_all(selector, attrs={"class": class_name})
    if elements and len(elements) > index:
        return elements[index].text.strip()
    return None


def _parse_match_date(soup: BeautifulSoup) -> str | None:
    element = soup.find("span", itemprop="startDate")
    if element:
        match_time = element.get("content", "")
        try:
            new_dt = match_time.split("+")[0]
            utc_time = datetime.strptime(new_dt, "%Y-%m-%dT%H:%M:%S")
            utc_time = utc_time.replace(tzinfo=pytz.UTC)
            ist = pytz.timezone("Asia/Kolkata")
            local_time = utc_time.astimezone(ist)
            return local_time.strftime("%Y-%m-%d %I:%M:%S %p IST")
        except (ValueError, IndexError):
            return None
    return None


def _timestamp_to_ist(ts_millis: str) -> str | None:
    """Convert a millisecond timestamp string to IST formatted date."""
    try:
        utc_time = datetime.fromtimestamp(int(ts_millis) / 1000, tz=pytz.UTC)
        ist = pytz.timezone("Asia/Kolkata")
        local_time = utc_time.astimezone(ist)
        return local_time.strftime("%Y-%m-%d %I:%M:%S %p IST")
    except (ValueError, TypeError, OSError):
        return None


def _extract_rsc_matches(html_text: str) -> list[dict]:
    """Extract match data from Cricbuzz Next.js RSC payload embedded in HTML."""
    soup = BeautifulSoup(html_text, "lxml")
    scripts = soup.find_all("script")

    for script in scripts:
        if script.string and "typeMatches" in script.string:
            rsc_match = re.search(
                r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', script.string, re.DOTALL
            )
            if not rsc_match:
                continue

            raw = rsc_match.group(1)
            unescaped = raw.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")

            idx = unescaped.find('"typeMatches"')
            if idx < 0:
                continue

            start = unescaped.rfind("{", max(0, idx - 500), idx)
            if start < 0:
                continue

            bracket_count = 0
            end_pos = start
            for j in range(start, len(unescaped)):
                char = unescaped[j]
                if char == "{":
                    bracket_count += 1
                elif char == "}":
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_pos = j + 1
                        break

            try:
                data = json.loads(unescaped[start:end_pos])
            except json.JSONDecodeError:
                continue

            all_matches: list[dict] = []
            for type_match in data.get("typeMatches", []):
                match_type = type_match.get("matchType", "Unknown")
                for series_match in type_match.get("seriesMatches", []):
                    wrapper = series_match.get("seriesAdWrapper", {})
                    if not wrapper:
                        continue
                    series_name = wrapper.get("seriesName", "")
                    for m in wrapper.get("matches", []):
                        info = m.get("matchInfo", {})
                        score_data = m.get("matchScore", {})
                        all_matches.append(
                            _format_match(info, score_data, match_type, series_name)
                        )
            return all_matches

    return []


def _format_score(score_obj: dict) -> str | None:
    """Format an innings score object into a readable string like '185/4 (20)'."""
    if not score_obj:
        return None
    inngs = score_obj.get("inngs1", {})
    if not inngs:
        return None
    runs = inngs.get("runs", "")
    wickets = inngs.get("wickets", "")
    overs = inngs.get("overs", "")
    parts = []
    if runs != "":
        parts.append(str(runs))
    if wickets != "":
        if parts:
            parts[-1] = f"{parts[-1]}/{wickets}"
        else:
            parts.append(f"/{wickets}")
    if overs != "":
        parts.append(f"({overs})")
    inngs2 = score_obj.get("inngs2", {})
    if inngs2:
        r2 = inngs2.get("runs", "")
        w2 = inngs2.get("wickets", "")
        o2 = inngs2.get("overs", "")
        second = ""
        if r2 != "":
            second = str(r2)
        if w2 != "":
            second = f"{second}/{w2}" if second else f"/{w2}"
        if o2 != "":
            second += f" ({o2})"
        if second:
            parts.append(f"& {second}")
    return " ".join(parts) if parts else None


def _format_match(
    info: dict, score_data: dict, match_type: str, series_name: str
) -> dict:
    """Format raw match info and score data into a clean API response dict."""
    team1 = info.get("team1", {})
    team2 = info.get("team2", {})
    venue = info.get("venueInfo", {})

    t1_score = _format_score(score_data.get("team1Score", {}))
    t2_score = _format_score(score_data.get("team2Score", {}))

    teams = []
    if team1:
        teams.append({
            "name": team1.get("teamName", ""),
            "short_name": team1.get("teamSName", ""),
            "score": t1_score,
        })
    if team2:
        teams.append({
            "name": team2.get("teamName", ""),
            "short_name": team2.get("teamSName", ""),
            "score": t2_score,
        })

    start_date = _timestamp_to_ist(info.get("startDate", ""))

    return {
        "match_id": str(info.get("matchId", "")),
        "title": f"{team1.get('teamName', '')} vs {team2.get('teamName', '')}, {info.get('matchDesc', '')}",
        "series": series_name,
        "match_type": match_type,
        "match_format": info.get("matchFormat", ""),
        "status": info.get("status", ""),
        "state": info.get("state", ""),
        "state_title": info.get("stateTitle", ""),
        "start_date": start_date,
        "venue": f"{venue.get('ground', '')}, {venue.get('city', '')}" if venue else None,
        "teams": teams,
    }


async def _fetch_cricbuzz_page(path: str) -> str:
    """Fetch a Cricbuzz page and return the HTML text."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(f"{BASE_URL}{path}", headers=_get_headers())
        r.raise_for_status()
        return r.text


async def fetch_live_matches() -> list[dict]:
    """Fetch all current live cricket matches from Cricbuzz."""
    try:
        html = await _fetch_cricbuzz_page("/cricket-match/live-scores")
    except httpx.HTTPError:
        return []
    return _extract_rsc_matches(html)


async def fetch_upcoming_matches() -> list[dict]:
    """Fetch upcoming cricket matches from Cricbuzz."""
    try:
        html = await _fetch_cricbuzz_page("/cricket-match/live-scores/upcoming-matches")
    except httpx.HTTPError:
        return []

    all_matches = _extract_rsc_matches(html)
    return [m for m in all_matches if m.get("state") in UPCOMING_STATES]


async def fetch_completed_matches() -> list[dict]:
    """Fetch recently completed cricket matches from Cricbuzz."""
    try:
        html = await _fetch_cricbuzz_page("/cricket-match/live-scores/recent-matches")
    except httpx.HTTPError:
        return []

    all_matches = _extract_rsc_matches(html)
    return [m for m in all_matches if m.get("state") in COMPLETED_STATES]


async def fetch_running_matches() -> list[dict]:
    """Fetch currently running (in-progress) cricket matches from Cricbuzz."""
    try:
        html = await _fetch_cricbuzz_page("/cricket-match/live-scores")
    except httpx.HTTPError:
        return []

    all_matches = _extract_rsc_matches(html)
    return [m for m in all_matches if m.get("state") in LIVE_STATES]


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

    soup = BeautifulSoup(r.content, "lxml")

    # Title
    title = _safe_text(soup, "h1", "cb-nav-hdr cb-font-18 line-ht24")
    if title:
        title = title.replace(", Commentary", "")

    # Status detection
    status_classes = [
        ("cb-col cb-col-100 cb-min-stts cb-text-complete", "completed"),
        ("cb-text-inprogress", "in_progress"),
        ("cb-col cb-col-100 cb-font-18 cb-toss-sts cb-text-abandon", "abandoned"),
        ("cb-text-stumps", "stumps"),
        ("cb-text-lunch", "lunch"),
        ("cb-text-inningsbreak", "innings_break"),
        ("cb-text-tea", "tea"),
        ("cb-text-rain", "rain_delay"),
        ("cb-text-wetoutfield", "wet_outfield"),
    ]

    status_text = None
    status_type = "upcoming"
    for cls, stype in status_classes:
        text = _safe_text(soup, "div", cls)
        if text:
            status_text = text
            status_type = stype
            break

    if not status_text:
        match_date = _parse_match_date(soup)
        if match_date:
            status_text = f"Starts at {match_date}"
            status_type = "upcoming"
        else:
            status_text = "Match Stats will Update Soon"

    # Live score
    live_score_el = soup.find("span", attrs={"class": "cb-font-20 text-bold"})
    live_score = live_score_el.text.strip() if live_score_el else None

    # Run rate
    run_rate_el = soup.find_all("span", attrs={"class": "cb-font-12 cb-text-gray"})
    run_rate = None
    if run_rate_el:
        run_rate = run_rate_el[0].text.strip().replace("CRR:\xa0", "")

    # Batsmen
    batters = []
    try:
        bat_names = soup.find_all("div", attrs={"class": "cb-col cb-col-50"})
        bat_runs = soup.find_all("div", attrs={"class": "cb-col cb-col-10 ab text-right"})
        bat_sr = soup.find_all("div", attrs={"class": "cb-col cb-col-14 ab text-right"})

        for i in range(2):
            name_idx = i + 1
            run_idx = i * 2
            ball_idx = i * 2 + 1
            if len(bat_names) > name_idx and len(bat_runs) > ball_idx and len(bat_sr) > i:
                batters.append({
                    "name": bat_names[name_idx].text.strip(),
                    "runs": bat_runs[run_idx].text.strip(),
                    "balls": bat_runs[ball_idx].text.strip(),
                    "strike_rate": bat_sr[i].text.strip(),
                })
    except (IndexError, AttributeError):
        pass

    # Bowlers
    bowlers = []
    try:
        bowl_names = soup.find_all("div", attrs={"class": "cb-col cb-col-50"})
        bowl_overs = soup.find_all("div", attrs={"class": "cb-col cb-col-10 text-right"})
        bowl_eco = soup.find_all("div", attrs={"class": "cb-col cb-col-14 text-right"})
        bowl_wickets = soup.find_all("div", attrs={"class": "cb-col cb-col-8 text-right"})

        for i in range(2):
            name_idx = i + 4
            over_idx = i * 2 + 4
            run_idx = i * 2 + 5
            eco_idx = i + 2
            wkt_idx = i * 2 + 5
            if (len(bowl_names) > name_idx and len(bowl_overs) > run_idx
                    and len(bowl_eco) > eco_idx and len(bowl_wickets) > wkt_idx):
                bowlers.append({
                    "name": bowl_names[name_idx].text.strip(),
                    "overs": bowl_overs[over_idx].text.strip(),
                    "runs_conceded": bowl_overs[run_idx].text.strip(),
                    "wickets": bowl_wickets[wkt_idx].text.strip(),
                    "economy": bowl_eco[eco_idx].text.strip(),
                })
    except (IndexError, AttributeError):
        pass

    return {
        "match_id": match_id,
        "title": title,
        "status": status_text,
        "status_type": status_type,
        "live_score": live_score,
        "run_rate": run_rate,
        "match_date": _parse_match_date(soup),
        "batters": batters,
        "bowlers": bowlers,
    }
