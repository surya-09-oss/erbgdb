"""Match processor — ties together scorecard scraping and fantasy points calculation.

For each completed/live match, fetches the scorecard, matches players against
the fantasy player database, and calculates per-player fantasy points.
Results are cached in memory keyed by match_id.
"""

import logging
import threading
from typing import Optional

from app.data import find_player, get_all_players
from app.fantasy.points import (
    calculate_batting_points,
    calculate_bowling_points,
    calculate_fielding_points,
    calculate_total_fantasy_points,
    parse_overs_to_float,
)
from app.fantasy.scorecard import fetch_full_scorecard, _count_lbw_bowled
from app.fantasy.player_history import record_player_match_points

logger = logging.getLogger(__name__)

# In-memory cache: match_id -> { player_name -> fantasy_points_dict }
_match_points_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


async def process_match(match_id: str, force_refresh: bool = False) -> dict:
    """Fetch scorecard for a match and calculate fantasy points for all players.

    Returns a dict with match_id and a list of player fantasy point entries.
    """
    # Check cache first
    if not force_refresh:
        with _cache_lock:
            if match_id in _match_points_cache:
                return _match_points_cache[match_id]

    scorecard = await fetch_full_scorecard(match_id)

    if scorecard.get("error"):
        return {
            "match_id": match_id,
            "error": scorecard["error"],
            "players": [],
        }

    innings_list = scorecard.get("innings", [])
    fielding_map = scorecard.get("fielding", {})
    all_players_db = get_all_players()

    # Build a lookup: lowercase player name -> player info
    player_lookup: dict[str, dict] = {}
    for team_code, players in all_players_db.items():
        for p in players:
            player_lookup[p["name"].lower().strip()] = p

    # Collect all player performances
    player_points: dict[str, dict] = {}

    # Process batting from all innings
    for innings in innings_list:
        batting_list = innings.get("batting", [])
        for batter in batting_list:
            name = batter["name"]
            name_lower = name.lower().strip()

            # Try to find this player in our database
            db_player = _fuzzy_find_player(name, player_lookup)

            role = db_player.get("role", "Unknown") if db_player else "Unknown"
            team = db_player.get("team", "unknown") if db_player else "unknown"
            is_bat_wk_ar = role.lower() in ("batsman", "wicket keeper", "wicketkeeper", "all rounder", "wk-batsman", "batter")

            batting_pts = calculate_batting_points(
                runs=int(batter.get("runs", 0)),
                balls=int(batter.get("balls", 0)),
                fours=int(batter.get("fours", 0)),
                sixes=int(batter.get("sixes", 0)),
                is_out=batter.get("is_out", False),
                is_batter_or_wk_or_allrounder=is_bat_wk_ar,
            )

            key = db_player["name"] if db_player else name
            if key not in player_points:
                player_points[key] = _empty_points(key, team, role, db_player)

            player_points[key]["batting"] = batting_pts
            player_points[key]["batting_stats"] = {
                "runs": int(batter.get("runs", 0)),
                "balls": int(batter.get("balls", 0)),
                "fours": int(batter.get("fours", 0)),
                "sixes": int(batter.get("sixes", 0)),
                "strike_rate": batter.get("strike_rate", 0),
                "is_out": batter.get("is_out", False),
            }

    # Process bowling from all innings
    for innings in innings_list:
        bowling_list = innings.get("bowling", [])
        batting_list = innings.get("batting", [])
        for bowler in bowling_list:
            name = bowler["name"]
            db_player = _fuzzy_find_player(name, player_lookup)

            role = db_player.get("role", "Unknown") if db_player else "Unknown"
            team = db_player.get("team", "unknown") if db_player else "unknown"

            overs_float = parse_overs_to_float(str(bowler.get("overs", 0)))
            lbw_bowled = _count_lbw_bowled(batting_list, name)

            bowling_pts = calculate_bowling_points(
                wickets=int(bowler.get("wickets", 0)),
                overs=overs_float,
                runs_conceded=int(bowler.get("runs_conceded", 0)),
                maidens=int(bowler.get("maidens", 0)),
                lbw_bowled_count=lbw_bowled,
            )

            key = db_player["name"] if db_player else name
            if key not in player_points:
                player_points[key] = _empty_points(key, team, role, db_player)

            player_points[key]["bowling"] = bowling_pts
            player_points[key]["bowling_stats"] = {
                "overs": bowler.get("overs", 0),
                "maidens": int(bowler.get("maidens", 0)),
                "runs_conceded": int(bowler.get("runs_conceded", 0)),
                "wickets": int(bowler.get("wickets", 0)),
                "economy": bowler.get("economy", 0),
            }

    # Process fielding
    for fielder_name, fielding_stats in fielding_map.items():
        db_player = _fuzzy_find_player(fielder_name, player_lookup)

        role = db_player.get("role", "Unknown") if db_player else "Unknown"
        team = db_player.get("team", "unknown") if db_player else "unknown"

        fielding_pts = calculate_fielding_points(
            catches=fielding_stats.get("catches", 0),
            stumpings=fielding_stats.get("stumpings", 0),
            run_out_direct=fielding_stats.get("run_out_direct", 0),
            run_out_assist=fielding_stats.get("run_out_assist", 0),
        )

        key = db_player["name"] if db_player else fielder_name
        if key not in player_points:
            player_points[key] = _empty_points(key, team, role, db_player)

        player_points[key]["fielding"] = fielding_pts
        player_points[key]["fielding_stats"] = fielding_stats

    # Calculate totals for each player
    results: list[dict] = []
    for name, data in player_points.items():
        total = calculate_total_fantasy_points(
            batting=data.get("batting"),
            bowling=data.get("bowling"),
            fielding=data.get("fielding"),
            playing_xi=True,
        )
        entry = {
            "name": name,
            "team": data.get("team", "unknown"),
            "role": data.get("role", "Unknown"),
            "image_url": data.get("image_url"),
            "fantasy_points": total,
        }
        if data.get("batting_stats"):
            entry["batting_stats"] = data["batting_stats"]
        if data.get("bowling_stats"):
            entry["bowling_stats"] = data["bowling_stats"]
        if data.get("fielding_stats"):
            entry["fielding_stats"] = data["fielding_stats"]
        results.append(entry)

    # Sort by total points descending
    results.sort(key=lambda x: x["fantasy_points"]["total_points"], reverse=True)

    # Record each player's match points into the per-player history store
    for player_entry in results:
        record_player_match_points(
            player_name=player_entry["name"],
            match_id=match_id,
            team=player_entry.get("team", "unknown"),
            role=player_entry.get("role", "Unknown"),
            image_url=player_entry.get("image_url"),
            fantasy_points=player_entry["fantasy_points"],
            batting_stats=player_entry.get("batting_stats"),
            bowling_stats=player_entry.get("bowling_stats"),
            fielding_stats=player_entry.get("fielding_stats"),
        )

    result = {
        "match_id": match_id,
        "players": results,
        "total_players": len(results),
    }

    # Cache it
    with _cache_lock:
        _match_points_cache[match_id] = result

    return result


def get_cached_match_points(match_id: str) -> Optional[dict]:
    """Get cached match points without fetching."""
    with _cache_lock:
        return _match_points_cache.get(match_id)


def clear_match_cache(match_id: Optional[str] = None) -> None:
    """Clear cached match points."""
    with _cache_lock:
        if match_id:
            _match_points_cache.pop(match_id, None)
        else:
            _match_points_cache.clear()


def _empty_points(name: str, team: str, role: str, db_player: Optional[dict]) -> dict:
    """Create an empty points structure for a player."""
    return {
        "name": name,
        "team": team,
        "role": role,
        "image_url": db_player.get("image_url") if db_player else None,
        "batting": None,
        "bowling": None,
        "fielding": None,
        "batting_stats": None,
        "bowling_stats": None,
        "fielding_stats": None,
    }


def _fuzzy_find_player(name: str, player_lookup: dict) -> Optional[dict]:
    """Try to find a player in the lookup by exact or fuzzy match."""
    name_lower = name.lower().strip()

    # Exact match
    if name_lower in player_lookup:
        return player_lookup[name_lower]

    # Try matching last name
    name_parts = name_lower.split()
    if name_parts:
        last_name = name_parts[-1]
        matches = [
            p for key, p in player_lookup.items()
            if key.split()[-1] == last_name
        ]
        if len(matches) == 1:
            return matches[0]

    # Try partial match
    for key, player in player_lookup.items():
        if name_lower in key or key in name_lower:
            return player

    return None
