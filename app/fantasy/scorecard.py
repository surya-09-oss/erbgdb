"""Cricbuzz scorecard scraper — extracts structured batting/bowling/fielding stats
from Cricbuzz's Next.js RSC (React Server Components) payload so fantasy points
can be calculated per player.

The old HTML-table parser no longer works because Cricbuzz moved to a Next.js RSC
architecture where scorecard data is embedded as JSON inside ``self.__next_f.push``
script chunks.  This module now extracts the ``scorecardApiData`` JSON object
directly, which contains ``scoreCard`` (per-innings batting + bowling data) and
``matchHeader`` (match metadata).
"""

import logging
import re

import httpx

from app.scrapers.cricbuzz import _fetch_cricbuzz_page, _extract_rsc_key_object

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
            f"/live-cricket-scorecard/{match_id}"
        )
    except httpx.HTTPError:
        return {"match_id": match_id, "error": "Failed to fetch scorecard", "innings": []}

    return _parse_scorecard_rsc(match_id, html)


def _parse_scorecard_rsc(match_id: str, html: str) -> dict:
    """Parse Cricbuzz scorecard page by extracting the scorecardApiData JSON
    from the RSC payload embedded in the HTML."""

    scorecard_data = _extract_rsc_key_object(html, "scorecardApiData")

    if not scorecard_data:
        logger.warning("Could not extract scorecardApiData for match %s", match_id)
        return {"match_id": match_id, "error": "Could not parse scorecard data", "innings": []}

    score_cards = scorecard_data.get("scoreCard", [])
    match_header = scorecard_data.get("matchHeader", {})

    if not score_cards:
        state = match_header.get("state", "")
        if state in ("Toss", "Preview", "Upcoming"):
            return {
                "match_id": match_id,
                "innings": [],
                "fielding": {},
                "match_state": state,
                "status": match_header.get("status", "Match has not started yet"),
            }
        return {"match_id": match_id, "error": "No scorecard data available yet", "innings": []}

    innings_list: list[dict] = []
    fielding_map: dict[str, dict] = {}

    for idx, innings_data in enumerate(score_cards):
        parsed = _parse_rsc_innings(innings_data, fielding_map, idx + 1)
        if parsed and (parsed.get("batting") or parsed.get("bowling")):
            innings_list.append(parsed)

    return {
        "match_id": match_id,
        "innings": innings_list,
        "fielding": fielding_map,
    }


def _parse_rsc_innings(innings_data: dict, fielding_map: dict, innings_num: int) -> dict:
    """Parse a single innings from the RSC scoreCard entry."""
    batting: list[dict] = []
    bowling: list[dict] = []

    # --- Batting ---
    bat_team = innings_data.get("batTeamDetails", {})
    batsmen_data = bat_team.get("batsmenData", {})

    for _key, batter in batsmen_data.items():
        name = batter.get("batName", "")
        if not name:
            continue

        runs = int(batter.get("runs", 0))
        balls = int(batter.get("balls", 0))
        fours = int(batter.get("fours", 0))
        sixes = int(batter.get("sixes", 0))
        out_desc = batter.get("outDesc", "")
        wicket_code = batter.get("wicketCode", "")

        is_out = bool(wicket_code) and wicket_code.upper() not in ("", "NOT_OUT", "NOT OUT")

        batting.append({
            "name": name,
            "runs": runs,
            "balls": balls,
            "fours": fours,
            "sixes": sixes,
            "is_out": is_out,
            "dismissal": out_desc.lower() if out_desc else "",
            "wicket_code": wicket_code,
            "strike_rate": round((runs / balls) * 100, 2) if balls > 0 else 0.0,
        })

        # Extract fielding from structured data (fielderId) — preferred
        # Only fall back to dismissal text parsing if structured extraction
        # didn't find the fielder (to avoid double-counting).
        pre_count = len(fielding_map)
        _extract_fielding_from_structured(batter, wicket_code, fielding_map, innings_data)
        if len(fielding_map) == pre_count:
            _extract_fielding_from_dismissal(out_desc.lower() if out_desc else "", fielding_map)

    # --- Bowling ---
    bowl_team = innings_data.get("bowlTeamDetails", {})
    bowlers_data = bowl_team.get("bowlersData", {})

    for _key, bowler in bowlers_data.items():
        name = bowler.get("bowlName", "")
        if not name:
            continue

        overs_raw = bowler.get("overs", 0)
        maidens = int(bowler.get("maidens", 0))
        runs_conceded = int(bowler.get("runs", 0))
        wickets = int(bowler.get("wickets", 0))
        economy = bowler.get("economy", 0)

        try:
            overs_float = float(overs_raw)
        except (ValueError, TypeError):
            overs_float = 0.0

        bowling.append({
            "name": name,
            "overs": overs_raw,
            "maidens": maidens,
            "runs_conceded": runs_conceded,
            "wickets": wickets,
            "economy": round(float(economy), 2) if economy else (
                round(runs_conceded / overs_float, 2) if overs_float > 0 else 0.0
            ),
        })

    return {
        "innings_number": innings_num,
        "batting": batting,
        "bowling": bowling,
    }


def _extract_fielding_from_structured(
    batter: dict,
    wicket_code: str,
    fielding_map: dict,
    innings_data: dict,
) -> None:
    """Extract fielding credits from structured RSC batter data using
    fielderId1/2/3 and wicketCode fields."""
    if not wicket_code or wicket_code.upper() in ("", "NOT_OUT", "NOT OUT"):
        return

    wicket_upper = wicket_code.upper()

    if wicket_upper == "CAUGHT":
        fielder_id = batter.get("fielderId1", 0)
        if fielder_id:
            fielder_name = _resolve_fielder_name(fielder_id, innings_data)
            if fielder_name:
                _increment_fielding(fielding_map, fielder_name, "catches")

    elif wicket_upper == "STUMPED":
        fielder_id = batter.get("fielderId1", 0)
        if fielder_id:
            fielder_name = _resolve_fielder_name(fielder_id, innings_data)
            if fielder_name:
                _increment_fielding(fielding_map, fielder_name, "stumpings")

    elif wicket_upper in ("RUN_OUT", "RUNOUT", "RUN OUT"):
        fielder_id1 = batter.get("fielderId1", 0)
        fielder_id2 = batter.get("fielderId2", 0)
        if fielder_id1:
            fielder_name = _resolve_fielder_name(fielder_id1, innings_data)
            if fielder_name:
                _increment_fielding(fielding_map, fielder_name, "run_out_direct")
        if fielder_id2:
            fielder_name2 = _resolve_fielder_name(fielder_id2, innings_data)
            if fielder_name2:
                _increment_fielding(fielding_map, fielder_name2, "run_out_assist")

    elif wicket_upper in ("CAUGHT_AND_BOWLED", "CAUGHT AND BOWLED"):
        bowler_id = batter.get("bowlerId", 0)
        if bowler_id:
            bowler_name = _resolve_bowler_name(bowler_id, innings_data)
            if bowler_name:
                _increment_fielding(fielding_map, bowler_name, "catches")


def _resolve_fielder_name(fielder_id: int, innings_data: dict) -> str:
    """Try to resolve a fielder ID to a player name.
    Fielders are on the bowling team, so look in bowlTeamDetails.bowlersData."""
    if not fielder_id:
        return ""

    bowl_team = innings_data.get("bowlTeamDetails", {})
    bowlers = bowl_team.get("bowlersData", {})
    for _k, bowler in bowlers.items():
        if bowler.get("bowlerId") == fielder_id:
            return bowler.get("bowlName", "")
    return ""


def _resolve_bowler_name(bowler_id: int, innings_data: dict) -> str:
    """Resolve a bowler ID to name from bowlersData."""
    if not bowler_id:
        return ""
    bowl_team = innings_data.get("bowlTeamDetails", {})
    bowlers = bowl_team.get("bowlersData", {})
    for _k, bowler in bowlers.items():
        if bowler.get("bowlerId") == bowler_id:
            return bowler.get("bowlName", "")
    return ""


def _extract_fielding_from_dismissal(dismissal: str, fielding_map: dict) -> None:
    """Parse a dismissal string to credit fielders with catches, stumpings, run outs.
    This is a fallback when structured fielder ID resolution fails."""
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
    """Count how many batters a bowler dismissed via LBW or bowled.
    Works with both old-style dismissal text and new wicketCode field."""
    count = 0
    bowler_lower = bowler_name.lower().strip()
    for batter in innings_data:
        wicket_code = batter.get("wicket_code", "").upper()
        dismissal = batter.get("dismissal", "").lower()

        is_lbw_bowled = wicket_code in ("LBW", "BOWLED") or (
            ("lbw" in dismissal or "bowled" in dismissal or dismissal.startswith("b "))
        )
        if is_lbw_bowled and bowler_lower in dismissal:
            count += 1
    return count
