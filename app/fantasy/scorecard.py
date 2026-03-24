"""Cricbuzz scorecard scraper — fetches detailed batting/bowling/fielding stats
for a specific match so fantasy points can be calculated per player."""

import logging
import re

import httpx
from bs4 import BeautifulSoup, Tag

from app.scrapers.cricbuzz import _fetch_cricbuzz_page, _get_headers, BASE_URL

logger = logging.getLogger(__name__)


async def fetch_full_scorecard(match_id: str) -> dict:
    """Fetch the full scorecard for a match from Cricbuzz.

    Returns a dict with:
      - match_id
      - innings: list of innings, each with batting and bowling entries
      - fielding: aggregated fielding actions (catches, stumpings, run outs)
    """
    try:
        html = await _fetch_cricbuzz_page(
            f"/api/html/cricket-scorecard/{match_id}"
        )
    except httpx.HTTPError:
        # Try the regular scorecard page
        try:
            html = await _fetch_cricbuzz_page(
                f"/live-cricket-scorecard/{match_id}"
            )
        except httpx.HTTPError:
            return {"match_id": match_id, "error": "Failed to fetch scorecard", "innings": []}

    return _parse_scorecard_html(match_id, html)


def _parse_scorecard_html(match_id: str, html: str) -> dict:
    """Parse Cricbuzz scorecard HTML into structured data."""
    soup = BeautifulSoup(html, "lxml")
    innings_list: list[dict] = []
    fielding_map: dict[str, dict] = {}  # player_name -> {catches, stumpings, run_out_direct, run_out_assist}

    # Find all innings sections
    innings_divs = soup.find_all("div", id=re.compile(r"innings_\d+"))
    if not innings_divs:
        # Alternative: look for scorecard tables
        innings_divs = soup.find_all("div", class_=re.compile(r"cb-col cb-col-100 cb-ltst-wgt-hdr"))

    for idx, innings_div in enumerate(innings_divs):
        innings_data = _parse_innings(innings_div, fielding_map, idx + 1)
        if innings_data and (innings_data.get("batting") or innings_data.get("bowling")):
            innings_list.append(innings_data)

    # If no innings found via divs, try parsing tables directly
    if not innings_list:
        innings_list = _parse_scorecard_tables(soup, fielding_map)

    return {
        "match_id": match_id,
        "innings": innings_list,
        "fielding": fielding_map,
    }


def _parse_innings(div: Tag, fielding_map: dict, innings_num: int) -> dict:
    """Parse a single innings div into batting and bowling data."""
    batting: list[dict] = []
    bowling: list[dict] = []

    # Find batting entries
    bat_rows = div.find_all("div", class_=re.compile(r"cb-col cb-col-100 cb-scrd-itms"))
    for row in bat_rows:
        cols = row.find_all("div", class_=re.compile(r"cb-col"))
        if len(cols) < 2:
            continue

        first_col_text = cols[0].get_text(strip=True)
        # Skip header/extras/total rows
        if not first_col_text or first_col_text in ("Extras", "Total", "Fall of Wickets"):
            continue

        # Check if this is a batter row (has a link to player profile)
        player_link = cols[0].find("a")
        if not player_link:
            continue

        player_name = player_link.get_text(strip=True)
        if not player_name:
            continue

        # Try to determine dismissal info
        dismissal_text = ""
        if len(cols) > 1:
            dismissal_col = cols[1] if len(cols) > 1 else None
            if dismissal_col:
                dismissal_text = dismissal_col.get_text(strip=True).lower()

        # Parse numeric stats
        stats = _extract_numeric_cols(cols[2:])
        runs = stats[0] if len(stats) > 0 else 0
        balls = stats[1] if len(stats) > 1 else 0
        fours = stats[2] if len(stats) > 2 else 0
        sixes = stats[3] if len(stats) > 3 else 0

        is_out = "not out" not in dismissal_text and dismissal_text != ""
        is_duck = runs == 0 and is_out

        batting.append({
            "name": player_name,
            "runs": runs,
            "balls": balls,
            "fours": fours,
            "sixes": sixes,
            "is_out": is_out,
            "dismissal": dismissal_text,
            "strike_rate": round((runs / balls) * 100, 2) if balls > 0 else 0.0,
        })

        # Parse fielding from dismissal text
        _extract_fielding_from_dismissal(dismissal_text, fielding_map)

    # Find bowling entries - look for bowling table
    bowl_section = div.find_all("div", class_=re.compile(r"cb-col cb-col-100 cb-scrd-itms"))
    in_bowling = False
    for row in bowl_section:
        text = row.get_text(strip=True)
        if "BOWLING" in text.upper():
            in_bowling = True
            continue
        if not in_bowling:
            continue

        cols = row.find_all("div", class_=re.compile(r"cb-col"))
        if len(cols) < 2:
            continue

        player_link = cols[0].find("a")
        if not player_link:
            continue

        bowler_name = player_link.get_text(strip=True)
        if not bowler_name:
            continue

        stats = _extract_numeric_cols(cols[1:])
        overs = stats[0] if len(stats) > 0 else 0
        maidens = stats[1] if len(stats) > 1 else 0
        runs_conceded = stats[2] if len(stats) > 2 else 0
        wickets = stats[3] if len(stats) > 3 else 0

        bowling.append({
            "name": bowler_name,
            "overs": overs,
            "maidens": maidens,
            "runs_conceded": runs_conceded,
            "wickets": wickets,
            "economy": round(runs_conceded / overs, 2) if overs > 0 else 0.0,
        })

    return {
        "innings_number": innings_num,
        "batting": batting,
        "bowling": bowling,
    }


def _parse_scorecard_tables(soup: BeautifulSoup, fielding_map: dict) -> list[dict]:
    """Fallback parser that looks for scorecard data in table format."""
    innings_list: list[dict] = []

    tables = soup.find_all("table")
    current_batting: list[dict] = []
    current_bowling: list[dict] = []
    innings_num = 0

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # Detect if this is a batting or bowling table by headers
        header = rows[0].get_text(strip=True).lower()

        if "batter" in header or "batsman" in header or "batting" in header:
            innings_num += 1
            current_batting = []
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 6:
                    continue
                name_cell = cells[0]
                player_link = name_cell.find("a")
                name = player_link.get_text(strip=True) if player_link else name_cell.get_text(strip=True)
                if not name or name.lower() in ("extras", "total"):
                    continue

                dismissal = cells[1].get_text(strip=True).lower() if len(cells) > 1 else ""
                nums = []
                for c in cells[2:]:
                    try:
                        nums.append(int(c.get_text(strip=True)))
                    except ValueError:
                        nums.append(0)

                runs = nums[0] if nums else 0
                balls = nums[1] if len(nums) > 1 else 0
                fours = nums[2] if len(nums) > 2 else 0
                sixes = nums[3] if len(nums) > 3 else 0

                is_out = "not out" not in dismissal and dismissal != ""
                current_batting.append({
                    "name": name,
                    "runs": runs,
                    "balls": balls,
                    "fours": fours,
                    "sixes": sixes,
                    "is_out": is_out,
                    "dismissal": dismissal,
                    "strike_rate": round((runs / balls) * 100, 2) if balls > 0 else 0.0,
                })
                _extract_fielding_from_dismissal(dismissal, fielding_map)

        elif "bowler" in header or "bowling" in header:
            current_bowling = []
            for row in rows[1:]:
                cells = row.find_all("td")
                if len(cells) < 5:
                    continue
                name_cell = cells[0]
                player_link = name_cell.find("a")
                name = player_link.get_text(strip=True) if player_link else name_cell.get_text(strip=True)
                if not name:
                    continue

                nums: list[float] = []
                for c in cells[1:]:
                    try:
                        nums.append(float(c.get_text(strip=True)))
                    except ValueError:
                        nums.append(0)

                overs = nums[0] if nums else 0
                maidens = int(nums[1]) if len(nums) > 1 else 0
                runs_conceded = int(nums[2]) if len(nums) > 2 else 0
                wickets = int(nums[3]) if len(nums) > 3 else 0

                current_bowling.append({
                    "name": name,
                    "overs": overs,
                    "maidens": maidens,
                    "runs_conceded": runs_conceded,
                    "wickets": wickets,
                    "economy": round(runs_conceded / overs, 2) if overs > 0 else 0.0,
                })

            # After bowling table, save the complete innings
            if current_batting or current_bowling:
                innings_list.append({
                    "innings_number": innings_num,
                    "batting": current_batting,
                    "bowling": current_bowling,
                })
                current_batting = []
                current_bowling = []

    # If we have leftover data
    if current_batting or current_bowling:
        innings_list.append({
            "innings_number": innings_num,
            "batting": current_batting,
            "bowling": current_bowling,
        })

    return innings_list


def _extract_numeric_cols(cols: list) -> list[float]:
    """Extract numeric values from a list of HTML column elements."""
    values: list[float] = []
    for col in cols:
        text = col.get_text(strip=True)
        try:
            values.append(float(text))
        except (ValueError, TypeError):
            pass
    return values


def _extract_fielding_from_dismissal(dismissal: str, fielding_map: dict) -> None:
    """Parse a dismissal string to credit fielders with catches, stumpings, run outs."""
    if not dismissal:
        return

    # Caught: "c PlayerName b BowlerName"
    caught_match = re.search(r"c\s+([a-zA-Z\s.']+?)\s+b\s+", dismissal)
    if caught_match:
        catcher = caught_match.group(1).strip()
        if catcher and catcher.lower() not in ("sub", "and", ""):
            _increment_fielding(fielding_map, catcher, "catches")

    # Stumped: "st PlayerName b BowlerName"
    stumped_match = re.search(r"st\s+([a-zA-Z\s.']+?)\s+b\s+", dismissal)
    if stumped_match:
        keeper = stumped_match.group(1).strip()
        if keeper:
            _increment_fielding(fielding_map, keeper, "stumpings")

    # Run out (direct): "run out (PlayerName)"
    runout_match = re.search(r"run out\s*\(([^)]+)\)", dismissal)
    if runout_match:
        fielders_text = runout_match.group(1).strip()
        fielders = [f.strip() for f in fielders_text.split("/")]
        if len(fielders) == 1:
            _increment_fielding(fielding_map, fielders[0], "run_out_direct")
        else:
            # First fielder gets direct hit, rest get assist
            _increment_fielding(fielding_map, fielders[0], "run_out_direct")
            for f in fielders[1:]:
                _increment_fielding(fielding_map, f, "run_out_assist")


def _increment_fielding(fielding_map: dict, player_name: str, field: str) -> None:
    """Increment a fielding stat for a player."""
    if not player_name or player_name.lower() in ("sub", ""):
        return
    if player_name not in fielding_map:
        fielding_map[player_name] = {
            "catches": 0,
            "stumpings": 0,
            "run_out_direct": 0,
            "run_out_assist": 0,
        }
    fielding_map[player_name][field] = fielding_map[player_name].get(field, 0) + 1


def _count_lbw_bowled(innings_data: list[dict], bowler_name: str) -> int:
    """Count how many batters a bowler dismissed via LBW or bowled."""
    count = 0
    bowler_lower = bowler_name.lower().strip()
    for batter in innings_data:
        dismissal = batter.get("dismissal", "").lower()
        if ("lbw" in dismissal or "bowled" in dismissal or dismissal.startswith("b ")) and bowler_lower in dismissal:
            count += 1
    return count
