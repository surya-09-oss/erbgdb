"""Cricbuzz scraper - scrapes live cricket data from Cricbuzz.com."""

import asyncio
import json
import logging
import random
import re

import httpx
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

BASE_URL = "https://www.cricbuzz.com"

# Match states from Cricbuzz
LIVE_STATES = {"In Progress", "Toss", "Stumps", "Lunch", "Tea", "Innings Break", "Drink"}
COMPLETED_STATES = {"Complete", "Abandoned", "No Result"}
UPCOMING_STATES = {"Preview", "Upcoming"}


MAX_RETRIES = 3
RETRY_BACKOFF = 1.0


def _get_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
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
    """Fetch a Cricbuzz page with retry logic and return the HTML text."""
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=True,
                http2=False,
            ) as client:
                r = await client.get(f"{BASE_URL}{path}", headers=_get_headers())
                r.raise_for_status()
                return r.text
        except (httpx.HTTPError, httpx.StreamError) as exc:
            last_exc = exc
            logger.warning(
                "Cricbuzz fetch attempt %d/%d failed for %s: %s",
                attempt + 1, MAX_RETRIES, path, exc,
            )
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BACKOFF * (attempt + 1))
    raise last_exc or httpx.HTTPError("All retry attempts failed")


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


def _extract_rsc_json(html_text: str, key: str) -> dict | None:
    """Extract a JSON object containing `key` from Cricbuzz Next.js RSC payload."""
    soup = BeautifulSoup(html_text, "lxml")
    scripts = soup.find_all("script")
    for script in scripts:
        if not script.string or key not in script.string:
            continue
        rsc_chunks = re.findall(
            r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', script.string, re.DOTALL
        )
        for raw in rsc_chunks:
            unescaped = raw.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")
            idx = unescaped.find(f'"{key}"')
            if idx < 0:
                continue
            start = unescaped.rfind("{", max(0, idx - 1000), idx)
            if start < 0:
                continue
            bracket_count = 0
            end_pos = start
            for j in range(start, min(len(unescaped), start + 500000)):
                c = unescaped[j]
                if c == "{":
                    bracket_count += 1
                elif c == "}":
                    bracket_count -= 1
                    if bracket_count == 0:
                        end_pos = j + 1
                        break
            try:
                return json.loads(unescaped[start:end_pos])
            except json.JSONDecodeError:
                continue
    return None


# ---------------------------------------------------------------------------
# IPL series constants
# ---------------------------------------------------------------------------
IPL_SERIES_ID = 9241
IPL_SERIES_SLUG = "indian-premier-league-2026"

# Mapping of short team codes to Cricbuzz squad IDs and full names
IPL_SQUAD_MAP: dict[str, dict] = {
    "csk": {"squad_id": 99705, "team_id": 58, "name": "Chennai Super Kings"},
    "dc": {"squad_id": 99716, "team_id": 61, "name": "Delhi Capitals"},
    "gt": {"squad_id": 99727, "team_id": 971, "name": "Gujarat Titans"},
    "rcb": {"squad_id": 99738, "team_id": 59, "name": "Royal Challengers Bengaluru"},
    "pk": {"squad_id": 99749, "team_id": 65, "name": "Punjab Kings"},
    "kkr": {"squad_id": 99760, "team_id": 63, "name": "Kolkata Knight Riders"},
    "srh": {"squad_id": 99771, "team_id": 255, "name": "Sunrisers Hyderabad"},
    "rr": {"squad_id": 99782, "team_id": 64, "name": "Rajasthan Royals"},
    "lsg": {"squad_id": 99793, "team_id": 966, "name": "Lucknow Super Giants"},
    "mi": {"squad_id": 99804, "team_id": 62, "name": "Mumbai Indians"},
}


async def fetch_ipl_schedule_from_cricbuzz() -> dict:
    """Fetch the IPL schedule from Cricbuzz series page."""
    try:
        html = await _fetch_cricbuzz_page(
            f"/cricket-series/{IPL_SERIES_ID}/{IPL_SERIES_SLUG}/matches"
        )
    except httpx.HTTPError:
        return {"error": "Failed to fetch IPL schedule from Cricbuzz", "status_code": 503}

    data = _extract_rsc_json(html, "matchDetails")
    if not data:
        return {"error": "Could not parse IPL schedule data", "status_code": 502}

    matches_data = data.get("matchesData", data)
    match_details = matches_data.get("matchDetails", [])

    schedule: list[dict] = []
    for entry in match_details:
        if not isinstance(entry, dict):
            continue
        mdm = entry.get("matchDetailsMap", {})
        date_key = mdm.get("key", "")
        for m in mdm.get("match", []):
            info = m.get("matchInfo", {})
            score = m.get("matchScore", {})
            team1 = info.get("team1", {})
            team2 = info.get("team2", {})
            t1_score = _format_score(score.get("team1Score", {}))
            t2_score = _format_score(score.get("team2Score", {}))
            venue = info.get("venueInfo", {})
            schedule.append({
                "match_id": str(info.get("matchId", "")),
                "date": date_key,
                "match_desc": info.get("matchDesc", ""),
                "status": info.get("status", ""),
                "state": info.get("state", ""),
                "team1": {
                    "name": team1.get("teamName", ""),
                    "short_name": team1.get("teamSName", ""),
                    "score": t1_score,
                },
                "team2": {
                    "name": team2.get("teamName", ""),
                    "short_name": team2.get("teamSName", ""),
                    "score": t2_score,
                },
                "venue": f"{venue.get('ground', '')}, {venue.get('city', '')}" if venue else None,
                "start_date": _timestamp_to_ist(info.get("startDate", "")),
            })

    return {"series": "Indian Premier League 2026", "matches": schedule, "total": len(schedule)}


async def fetch_ipl_points_table_from_cricbuzz() -> dict:
    """Fetch the IPL points table from Cricbuzz series page."""
    try:
        html = await _fetch_cricbuzz_page(
            f"/cricket-series/{IPL_SERIES_ID}/{IPL_SERIES_SLUG}/points-table"
        )
    except httpx.HTTPError:
        return {"error": "Failed to fetch IPL points table from Cricbuzz", "status_code": 503}

    data = _extract_rsc_json(html, "pointsTable")
    if not data:
        return {"error": "Could not parse IPL points table data", "status_code": 502}

    pts_data = data.get("pointsTableData", data)
    points_table_list = pts_data.get("pointsTable", [])

    teams: list[dict] = []
    for group in points_table_list:
        for team_info in group.get("pointsTableInfo", []):
            teams.append({
                "team": team_info.get("teamFullName", ""),
                "short_name": team_info.get("teamName", ""),
                "played": team_info.get("matchesPlayed", 0),
                "won": team_info.get("matchesWon", 0),
                "lost": team_info.get("matchesLost", 0),
                "tied": team_info.get("matchesTied", 0),
                "no_result": team_info.get("noRes", 0),
                "nrr": team_info.get("nrr", "0.000"),
                "points": team_info.get("points", 0),
            })

    return {
        "series": pts_data.get("seriesName", "Indian Premier League 2026"),
        "teams": teams,
        "total": len(teams),
    }


async def fetch_ipl_live_scores_from_cricbuzz() -> dict:
    """Fetch live IPL match scores from Cricbuzz."""
    all_matches = await fetch_live_matches()
    ipl_matches = [
        m for m in all_matches
        if "indian premier league" in m.get("series", "").lower()
        or "ipl" in m.get("series", "").lower()
    ]
    return {
        "series": "Indian Premier League 2026",
        "matches": ipl_matches,
        "total": len(ipl_matches),
    }


# IPL 2026 squad data (static for the season, sourced from official announcements)
IPL_SQUADS: dict[str, list[str]] = {
    "csk": [
        "Ruturaj Gaikwad", "MS Dhoni", "Sanju Samson", "Shivam Dube",
        "Dewald Brevis", "Ayush Mhatre", "Urvil Patel", "Noor Ahmad",
        "Nathan Ellis", "Shreyas Gopal", "Khaleel Ahmed", "Ramakrishna Ghosh",
        "Mukesh Choudhary", "Jamie Overton", "Gurjapneet Singh", "Anshul Kamboj",
        "Akeal Hosein", "Prashant Veer", "Kartik Sharma", "Matthew Short",
        "Aman Khan", "Sarfaraz Khan", "Rahul Chahar", "Matt Henry", "Zak Foulkes",
    ],
    "dc": [
        "KL Rahul", "Axar Patel", "Kuldeep Yadav", "Mitchell Starc",
        "Tristan Stubbs", "Abishek Porel", "T. Natarajan", "Karun Nair",
        "Sameer Rizvi", "Ashutosh Sharma", "Vipraj Nigam", "Ajay Mandal",
        "Tripurana Vijay", "Madhav Tiwari", "Mukesh Kumar", "Dushmantha Chameera",
        "Nitish Rana", "Auqib Nabi Dar", "Ben Duckett", "David Miller",
        "Pathum Nissanka", "Lungi Ngidi", "Sahil Parakh", "Prithvi Shaw",
        "Kyle Jamieson",
    ],
    "gt": [
        "Shubman Gill", "Rashid Khan", "Sai Sudharsan", "Rahul Tewatia",
        "Shahrukh Khan", "Jos Buttler", "Kagiso Rabada", "Mohammed Siraj",
        "Prasidh Krishna", "Nishant Sindhu", "Kumar Kushagra", "Anuj Rawat",
        "Manav Suthar", "Washington Sundar", "Arshad Khan", "Gurnoor Brar",
        "Sai Kishore", "Ishant Sharma", "Jayant Yadav", "Glenn Phillips",
        "Ashok Sharma", "Jason Holder", "Tom Banton", "Luke Wood",
        "Prithviraj Yarra",
    ],
    "kkr": [
        "Ajinkya Rahane", "Rinku Singh", "Sunil Narine", "Varun Chakaravarthy",
        "Harshit Rana", "Ramandeep Singh", "Angkrish Raghuvanshi", "Vaibhav Arora",
        "Rovman Powell", "Manish Pandey", "Umran Malik", "Anukul Roy",
        "Cameron Green", "Matheesha Pathirana", "Finn Allen", "Tejasvi Singh Dahiya",
        "Kartik Tyagi", "Prashant Solanki", "Rahul Tripathi", "Tim Seifert",
        "Sarthak Ranjan", "Daksh Kamra", "Akash Deep", "Rachin Ravindra",
    ],
    "lsg": [
        "Rishabh Pant", "Nicholas Pooran", "Mayank Yadav", "Mohsin Khan",
        "Ayush Badoni", "Abdul Samad", "Aiden Markram", "Mitchell Marsh",
        "Avesh Khan", "Shahbaz Ahmed", "Arshin Kulkarni", "Himmat Singh",
        "Matthew Breetzke", "M. Siddharth", "Digvesh Rathi", "Prince Yadav",
        "Akash Singh", "Arjun Tendulkar", "Mohammed Shami", "Anrich Nortje",
        "Wanindu Hasaranga", "Mukul Choudhary", "Naman Tiwari",
        "Akshat Raghuvanshi", "Josh Inglis",
    ],
    "mi": [
        "Rohit Sharma", "Suryakumar Yadav", "Hardik Pandya", "Jasprit Bumrah",
        "Tilak Varma", "Trent Boult", "Robin Minz", "Ryan Rickelton",
        "Naman Dhir", "Mitchell Santner", "Will Jacks", "Corbin Bosch",
        "Raj Bawa", "Deepak Chahar", "Ashwani Kumar", "Raghu Sharma",
        "Allah Ghazanfar", "Shardul Thakur", "Sherfane Rutherford",
        "Mayank Markande", "Quinton de Kock", "Atharva Ankolekar",
        "Mohammad Izhar", "Danish Malewar", "Mayank Rawat",
    ],
    "pk": [
        "Shreyas Iyer", "Arshdeep Singh", "Prabhsimran Singh", "Shashank Singh",
        "Nehal Wadhera", "Marcus Stoinis", "Harpreet Brar", "Marco Jansen",
        "Azmatullah Omarzai", "Lockie Ferguson", "Yuzvendra Chahal",
        "Musheer Khan", "Priyansh Arya", "Pyla Avinash", "Harnoor Pannu",
        "Suryansh Shedge", "Mitch Owen", "Xavier Bartlett", "Vijaykumar Vyshak",
        "Yash Thakur", "Ben Dwarshuis", "Cooper Connolly", "Pravin Dubey",
        "Vishal Nishad",
    ],
    "rr": [
        "Yashasvi Jaiswal", "Riyan Parag", "Dhruv Jurel", "Shimron Hetmyer",
        "Ravindra Jadeja", "Jofra Archer", "Sam Curran", "Tushar Deshpande",
        "Sandeep Sharma", "Kwena Maphaka", "Nandre Burger", "Lhuan-dre Pretorius",
        "Donovan Ferreira", "Shubham Dubey", "Vaibhav Suryavanshi",
        "Yudhvir Singh Charak", "Ravi Bishnoi", "Adam Milne", "Ravi Singh",
        "Sushant Mishra", "Kuldeep Sen", "Yash Raj Punja", "Vignesh Puthur",
        "Brijesh Sharma", "Aman Rao",
    ],
    "rcb": [
        "Virat Kohli", "Rajat Patidar", "Phil Salt", "Jitesh Sharma",
        "Devdutt Padikkal", "Krunal Pandya", "Tim David", "Romario Shepherd",
        "Jacob Bethell", "Josh Hazlewood", "Yash Dayal", "Bhuvneshwar Kumar",
        "Nuwan Thushara", "Rasikh Salam", "Swapnil Singh", "Abhinandan Singh",
        "Suyash Sharma", "Venkatesh Iyer", "Mangesh Yadav", "Jacob Duffy",
        "Jordan Cox", "Satvik Deswal", "Vicky Ostwal", "Vihaan Malhotra",
        "Kanishk Chouhan",
    ],
    "srh": [
        "Pat Cummins", "Travis Head", "Heinrich Klaasen", "Abhishek Sharma",
        "Ishan Kishan", "Nitish Kumar Reddy", "Harshal Patel", "Jaydev Unadkat",
        "Brydon Carse", "Kamindu Mendis", "Eshan Malinga", "Zeeshan Ansari",
        "Aniket Verma", "R. Smaran", "Harsh Dubey", "Liam Livingstone",
        "Jack Edwards", "Salil Arora", "Shivam Mavi", "Shivang Kumar",
        "Krains Fuletra", "Praful Hinge", "Amit Kumar", "Onkar Tarmale",
        "Sakib Hussain",
    ],
}


async def fetch_ipl_squad_from_cricbuzz(team_code: str) -> dict:
    """Return IPL team squad data."""
    team_code = team_code.lower().strip()
    if team_code not in IPL_SQUAD_MAP:
        return {
            "error": f"Invalid team code '{team_code}'",
            "valid_codes": list(IPL_SQUAD_MAP.keys()),
            "status_code": 400,
        }

    team_info = IPL_SQUAD_MAP[team_code]
    players = [{"name": name} for name in IPL_SQUADS.get(team_code, [])]

    return {
        "team": team_info["name"],
        "team_code": team_code,
        "players": players,
        "total": len(players),
    }


def _extract_rsc_key_object(html_text: str, key: str) -> dict | None:
    """Extract a specific JSON object value for `key` from Cricbuzz RSC payload.

    Searches all ``self.__next_f.push`` chunks for ``"<key>":{...}`` and returns
    the parsed dict, or *None* if not found.
    """
    soup = BeautifulSoup(html_text, "lxml")
    scripts = soup.find_all("script")
    for script in scripts:
        if not script.string or key not in script.string:
            continue
        chunks = re.findall(
            r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', script.string, re.DOTALL,
        )
        for raw in chunks:
            if key not in raw:
                continue
            unescaped = raw.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")
            idx = unescaped.find(f'"{key}"')
            if idx < 0:
                continue
            colon = unescaped.find(":", idx + len(key) + 2)
            brace = unescaped.find("{", colon)
            if brace < 0:
                continue
            depth = 0
            end = brace
            for j in range(brace, min(len(unescaped), brace + 100000)):
                if unescaped[j] == "{":
                    depth += 1
                elif unescaped[j] == "}":
                    depth -= 1
                    if depth == 0:
                        end = j + 1
                        break
            try:
                return json.loads(unescaped[brace:end])
            except json.JSONDecodeError:
                continue
    return None


async def fetch_match_score(match_id: str) -> dict:
    """Fetch detailed live score for a specific match from Cricbuzz.

    Uses the RSC (React Server Components) payload embedded in the page HTML
    to extract structured match data (matchHeader + miniscore).
    """
    try:
        html = await _fetch_cricbuzz_page(f"/live-cricket-scores/{match_id}")
    except httpx.HTTPError:
        return {"error": "Failed to fetch match data", "match_id": match_id}

    # --- Extract matchHeader (always present) ---
    match_header = _extract_rsc_key_object(html, "matchHeader")

    if not match_header:
        # Fallback: return minimal info
        return {
            "match_id": match_id,
            "title": None,
            "status": "Match Stats will Update Soon",
            "status_type": "upcoming",
            "live_score": None,
            "run_rate": None,
            "match_date": None,
            "batters": [],
            "bowlers": [],
        }

    team1 = match_header.get("team1", {})
    team2 = match_header.get("team2", {})
    t1_name = team1.get("name", "")
    t2_name = team2.get("name", "")
    desc = match_header.get("matchDescription", "")
    title = f"{t1_name} vs {t2_name}, {desc}" if t1_name else None

    state = match_header.get("state", "")
    status_text = match_header.get("status", "")

    state_map = {
        "Complete": "completed",
        "In Progress": "in_progress",
        "Toss": "in_progress",
        "Stumps": "stumps",
        "Lunch": "lunch",
        "Tea": "tea",
        "Innings Break": "innings_break",
        "Drink": "in_progress",
        "Rain": "rain_delay",
        "Wet Outfield": "wet_outfield",
        "Abandoned": "abandoned",
        "Preview": "upcoming",
        "Upcoming": "upcoming",
    }
    status_type = state_map.get(state, "upcoming")

    # Match start timestamp
    match_date = None
    ts = match_header.get("matchStartTimestamp")
    if ts:
        match_date = _timestamp_to_ist(str(ts))

    # --- Extract miniscore (present when match is live / recently finished) ---
    miniscore = _extract_rsc_key_object(html, "miniscore")

    live_score = None
    run_rate = None
    batters: list[dict] = []
    bowlers: list[dict] = []

    if miniscore:
        # Current innings score
        bat_team = miniscore.get("battingTeam", {})
        if bat_team:
            innings = miniscore.get("currentInnings", bat_team)
            runs = bat_team.get("runs", innings.get("runs", ""))
            wickets = bat_team.get("wickets", innings.get("wickets", ""))
            overs = bat_team.get("overs", innings.get("overs", ""))
            if runs != "":
                live_score = f"{runs}/{wickets} ({overs})"

        run_rate = str(miniscore.get("currentRunRate", "")) or None
        if run_rate == "0" or run_rate == "0.0":
            run_rate = None

        # Current batters
        batter1 = miniscore.get("batsmanStriker", {})
        batter2 = miniscore.get("batsmanNonStriker", {})
        for b in [batter1, batter2]:
            if b and b.get("batName"):
                sr = 0.0
                balls = b.get("batBalls", 0)
                runs_b = b.get("batRuns", 0)
                if balls and int(balls) > 0:
                    sr = round(int(runs_b) / int(balls) * 100, 2)
                batters.append({
                    "name": b["batName"],
                    "runs": str(b.get("batRuns", 0)),
                    "balls": str(b.get("batBalls", 0)),
                    "fours": str(b.get("batFours", 0)),
                    "sixes": str(b.get("batSixes", 0)),
                    "strike_rate": str(sr),
                })

        # Current bowlers
        bowler1 = miniscore.get("bowlerStriker", {})
        bowler2 = miniscore.get("bowlerNonStriker", {})
        for bw in [bowler1, bowler2]:
            if bw and bw.get("bowlName"):
                bowlers.append({
                    "name": bw["bowlName"],
                    "overs": str(bw.get("bowlOvs", 0)),
                    "runs_conceded": str(bw.get("bowlRuns", 0)),
                    "wickets": str(bw.get("bowlWkts", 0)),
                    "maidens": str(bw.get("bowlMaidens", 0)),
                    "economy": str(bw.get("bowlEcon", 0)),
                })

    return {
        "match_id": match_id,
        "title": title,
        "status": status_text,
        "status_type": status_type,
        "live_score": live_score,
        "run_rate": run_rate,
        "match_date": match_date,
        "match_format": match_header.get("matchFormat", ""),
        "series": match_header.get("seriesName", ""),
        "teams": {
            "team1": {
                "name": t1_name,
                "short_name": team1.get("shortName", ""),
                "id": team1.get("id"),
            },
            "team2": {
                "name": t2_name,
                "short_name": team2.get("shortName", ""),
                "id": team2.get("id"),
            },
        },
        "batters": batters,
        "bowlers": bowlers,
    }
