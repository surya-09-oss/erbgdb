"""Cricket API scraper - compatible with sanwebinfo/cricket-api JSON format.

Scrapes live cricket data from Cricbuzz.com and returns it in the same
JSON structure used by https://github.com/sanwebinfo/cricket-api.
"""

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

NOT_FOUND = "Data Not Found"
UPDATING = "Match Stats will Update Soon"


def _get_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Cache-Control": "no-cache",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }


def _safe_find_text(
    soup: BeautifulSoup, tag: str, class_name: str, index: int = 0, fallback: str = UPDATING,
) -> str:
    elements = soup.find_all(tag, attrs={"class": class_name})
    if elements and len(elements) > index:
        return elements[index].text.strip()
    return fallback


def _parse_match_date_formatted(soup: BeautifulSoup) -> str:
    element = soup.find("span", itemprop="startDate")
    if element:
        match_time = element.get("content", "")
        try:
            aware_time = datetime.fromisoformat(match_time)
            ist = pytz.timezone("Asia/Kolkata")
            local_time = aware_time.astimezone(ist)
            return local_time.strftime(
                "Date: %Y-%m-%d - Time: %I:%M:%S %p (Indian Local Time)"
            )
        except (ValueError, IndexError):
            return UPDATING
    return UPDATING


def _resolve_status(soup: BeautifulSoup) -> str:
    update = _safe_find_text(
        soup, "div", "cb-col cb-col-100 cb-min-stts cb-text-complete"
    )
    if update != UPDATING:
        return update

    process = _safe_find_text(soup, "div", "cb-text-inprogress")
    if process != UPDATING:
        return process

    noresult = _safe_find_text(
        soup, "div", "cb-col cb-col-100 cb-font-18 cb-toss-sts cb-text-abandon"
    )
    if noresult != UPDATING:
        return noresult

    stumps = _safe_find_text(soup, "div", "cb-text-stumps")
    if stumps != UPDATING:
        return stumps

    lunch = _safe_find_text(soup, "div", "cb-text-lunch")
    if lunch != UPDATING:
        return lunch

    inningsbreak = _safe_find_text(soup, "div", "cb-text-inningsbreak")
    if inningsbreak != UPDATING:
        return inningsbreak

    tea = _safe_find_text(soup, "div", "cb-text-tea")
    if tea != UPDATING:
        return tea

    rain_break = _safe_find_text(soup, "div", "cb-text-rain")
    if rain_break != UPDATING:
        return rain_break

    wet_outfield = _safe_find_text(soup, "div", "cb-text-wetoutfield")
    if wet_outfield != UPDATING:
        return wet_outfield

    match_date = _parse_match_date_formatted(soup)
    if match_date != UPDATING:
        return match_date

    return "Match Stats will Update Soon..."


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

    soup = BeautifulSoup(r.content, "html.parser")

    try:
        title_el = soup.find("h1", attrs={"class": "cb-nav-hdr cb-font-18 line-ht24"})
        title = title_el.text.strip().replace(", Commentary", "") if title_el else NOT_FOUND

        live_score_el = soup.find("span", attrs={"class": "cb-font-20 text-bold"})
        live_score = live_score_el.text.strip() if live_score_el else NOT_FOUND

        run_rate_els = soup.find_all("span", attrs={"class": "cb-font-12 cb-text-gray"})
        run_rate = run_rate_els[0].text.strip().replace("CRR:\xa0", "") if run_rate_els else NOT_FOUND

        bat_names = soup.find_all("div", attrs={"class": "cb-col cb-col-50"})
        bat_runs = soup.find_all("div", attrs={"class": "cb-col cb-col-10 ab text-right"})
        bat_sr = soup.find_all("div", attrs={"class": "cb-col cb-col-14 ab text-right"})

        batter_one = bat_names[1].text.strip() if len(bat_names) > 1 else UPDATING
        batter_two = bat_names[2].text.strip() if len(bat_names) > 2 else UPDATING
        batter_one_run = bat_runs[0].text.strip() if len(bat_runs) > 0 else UPDATING
        batter_one_ball = bat_runs[1].text.strip() if len(bat_runs) > 1 else UPDATING
        batter_two_run = bat_runs[2].text.strip() if len(bat_runs) > 2 else UPDATING
        batter_two_ball = bat_runs[3].text.strip() if len(bat_runs) > 3 else UPDATING
        batter_one_sr = bat_sr[0].text.strip() if len(bat_sr) > 0 else UPDATING
        batter_two_sr = bat_sr[1].text.strip() if len(bat_sr) > 1 else UPDATING

        bowl_names = soup.find_all("div", attrs={"class": "cb-col cb-col-50"})
        bowl_overs = soup.find_all("div", attrs={"class": "cb-col cb-col-10 text-right"})
        bowl_eco = soup.find_all("div", attrs={"class": "cb-col cb-col-14 text-right"})
        bowl_wickets = soup.find_all("div", attrs={"class": "cb-col cb-col-8 text-right"})

        bowler_one = bowl_names[4].text.strip() if len(bowl_names) > 4 else UPDATING
        bowler_two = bowl_names[5].text.strip() if len(bowl_names) > 5 else UPDATING
        bowler_one_over = bowl_overs[4].text.strip() if len(bowl_overs) > 4 else UPDATING
        bowler_one_run = bowl_overs[5].text.strip() if len(bowl_overs) > 5 else UPDATING
        bowler_two_over = bowl_overs[6].text.strip() if len(bowl_overs) > 6 else UPDATING
        bowler_two_run = bowl_overs[7].text.strip() if len(bowl_overs) > 7 else UPDATING
        bowler_one_eco = bowl_eco[2].text.strip() if len(bowl_eco) > 2 else UPDATING
        bowler_two_eco = bowl_eco[3].text.strip() if len(bowl_eco) > 3 else UPDATING
        bowler_one_wicket = bowl_wickets[5].text.strip() if len(bowl_wickets) > 5 else UPDATING
        bowler_two_wicket = bowl_wickets[7].text.strip() if len(bowl_wickets) > 7 else UPDATING

    except (IndexError, AttributeError):
        title_el = soup.find("h1", attrs={"class": "cb-nav-hdr cb-font-18 line-ht24"})
        title = title_el.text.strip().replace(", Commentary", "") if title_el else NOT_FOUND

        live_score_el = soup.find("span", attrs={"class": "cb-font-20 text-bold"})
        live_score = live_score_el.text.strip() if live_score_el else NOT_FOUND

        run_rate = UPDATING
        batter_one = UPDATING
        batter_two = UPDATING
        batter_one_run = UPDATING
        batter_one_ball = UPDATING
        batter_two_run = UPDATING
        batter_two_ball = UPDATING
        batter_one_sr = UPDATING
        batter_two_sr = UPDATING
        bowler_one = UPDATING
        bowler_two = UPDATING
        bowler_one_over = UPDATING
        bowler_one_run = UPDATING
        bowler_two_over = UPDATING
        bowler_two_run = UPDATING
        bowler_one_eco = UPDATING
        bowler_two_eco = UPDATING
        bowler_one_wicket = UPDATING
        bowler_two_wicket = UPDATING

    status = _resolve_status(soup)

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
