"""Cricbuzz scraper - scrapes live cricket data from Cricbuzz.com."""

import random
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


async def fetch_live_matches() -> list[dict]:
    """Fetch all current live cricket matches from Cricbuzz."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(f"{BASE_URL}/cricket-match/live-scores", headers=_get_headers())
            r.raise_for_status()
        except httpx.HTTPError:
            return []

    soup = BeautifulSoup(r.content, "lxml")
    matches = []

    match_cards = soup.find_all("div", attrs={"class": "cb-mtch-lst cb-col cb-col-100 cb-tms-itm"})
    for card in match_cards:
        try:
            title_el = card.find("h3", attrs={"class": "cb-lv-scr-mtch-hdr"})
            title = title_el.text.strip() if title_el else None

            link_el = card.find("a", attrs={"class": "cb-lv-scrs-well"}) or card.find("a")
            match_id = None
            if link_el and link_el.get("href"):
                href = link_el["href"]
                parts = href.split("/")
                for i, part in enumerate(parts):
                    if part == "live-cricket-scores" and i + 1 < len(parts):
                        match_id = parts[i + 1]
                        break

            status_el = card.find("div", attrs={"class": "cb-text-live"}) or \
                        card.find("div", attrs={"class": "cb-text-complete"}) or \
                        card.find("div", attrs={"class": "cb-text-inprogress"}) or \
                        card.find("div", attrs={"class": "cb-text-stumps"})
            status = status_el.text.strip() if status_el else "Unknown"

            score_items = card.find_all("div", attrs={"class": "cb-col-100 cb-scr-wll-chvrn"})
            teams = []
            for item in score_items:
                team_name_el = item.find("div", attrs={"class": "cb-hmscg-tm-nm"})
                score_el = item.find("div", attrs={"class": "cb-hmscg-tm-nm cb-font-bold"}) or \
                           item.find("span", attrs={"class": "cb-font-20"})
                team_name = team_name_el.text.strip() if team_name_el else None
                score = score_el.text.strip() if score_el else None
                if team_name:
                    teams.append({"name": team_name, "score": score})

            if title or match_id:
                matches.append({
                    "match_id": match_id,
                    "title": title,
                    "status": status,
                    "teams": teams,
                })
        except (AttributeError, IndexError):
            continue

    return matches


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
