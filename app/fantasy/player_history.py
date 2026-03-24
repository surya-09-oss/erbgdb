"""Player match history — stores per-player, per-match fantasy points.

Each match's points start from 0. Old match data is preserved so you can
query any player's full history across all processed matches.
"""

import threading
from typing import Optional


# In-memory store: { player_name_lower: { match_id: { points_data } } }
_player_match_history: dict[str, dict[str, dict]] = {}
_history_lock = threading.Lock()


def record_player_match_points(
    player_name: str,
    match_id: str,
    team: str,
    role: str,
    image_url: Optional[str],
    fantasy_points: dict,
    batting_stats: Optional[dict] = None,
    bowling_stats: Optional[dict] = None,
    fielding_stats: Optional[dict] = None,
) -> None:
    """Record a player's fantasy points for a specific match.

    Each match entry is independent — points always start from 0 per match.
    """
    key = player_name.lower().strip()
    entry = {
        "player_name": player_name,
        "match_id": match_id,
        "team": team,
        "role": role,
        "image_url": image_url,
        "fantasy_points": fantasy_points,
        "batting_stats": batting_stats,
        "bowling_stats": bowling_stats,
        "fielding_stats": fielding_stats,
    }
    with _history_lock:
        if key not in _player_match_history:
            _player_match_history[key] = {}
        _player_match_history[key][match_id] = entry


def get_player_all_matches(player_name: str) -> list[dict]:
    """Get all match-wise points for a player, sorted by match_id."""
    key = player_name.lower().strip()
    with _history_lock:
        history = _player_match_history.get(key, {})
        matches = list(history.values())
    matches.sort(key=lambda x: x.get("match_id", ""))
    return matches


def get_player_match_points(player_name: str, match_id: str) -> Optional[dict]:
    """Get a player's fantasy points for a specific match."""
    key = player_name.lower().strip()
    with _history_lock:
        history = _player_match_history.get(key, {})
        return history.get(match_id)


def get_player_cumulative_total(player_name: str) -> dict:
    """Get cumulative total points for a player across all matches.

    Returns the sum of all match points along with per-match breakdown.
    """
    key = player_name.lower().strip()
    with _history_lock:
        history = _player_match_history.get(key, {})
        matches = list(history.values())

    if not matches:
        return {
            "player_name": player_name,
            "total_matches": 0,
            "cumulative_total_points": 0,
            "cumulative_batting_points": 0,
            "cumulative_bowling_points": 0,
            "cumulative_fielding_points": 0,
            "matches": [],
        }

    total_pts = 0
    total_bat = 0
    total_bowl = 0
    total_field = 0
    match_summaries: list[dict] = []

    for m in sorted(matches, key=lambda x: x.get("match_id", "")):
        fp = m.get("fantasy_points", {})
        match_total = fp.get("total_points", 0)
        bat_pts = fp.get("batting_points", 0)
        bowl_pts = fp.get("bowling_points", 0)
        field_pts = fp.get("fielding_points", 0)

        total_pts += match_total
        total_bat += bat_pts
        total_bowl += bowl_pts
        total_field += field_pts

        match_summaries.append({
            "match_id": m["match_id"],
            "points": match_total,
            "batting_points": bat_pts,
            "bowling_points": bowl_pts,
            "fielding_points": field_pts,
        })

    first = matches[0]
    return {
        "player_name": first.get("player_name", player_name),
        "team": first.get("team", "unknown"),
        "role": first.get("role", "Unknown"),
        "image_url": first.get("image_url"),
        "total_matches": len(matches),
        "cumulative_total_points": total_pts,
        "cumulative_batting_points": total_bat,
        "cumulative_bowling_points": total_bowl,
        "cumulative_fielding_points": total_field,
        "matches": match_summaries,
    }


def get_team_match_history(team_code: str) -> list[dict]:
    """Get match-wise points for all players belonging to a team."""
    team_lower = team_code.lower().strip()
    results: list[dict] = []
    with _history_lock:
        for _key, match_map in _player_match_history.items():
            for _mid, entry in match_map.items():
                if entry.get("team", "").lower() == team_lower:
                    results.append(entry)
    results.sort(key=lambda x: (x.get("match_id", ""), x.get("player_name", "")))
    return results


def get_all_recorded_players() -> list[str]:
    """Return a list of all player names that have recorded match history."""
    with _history_lock:
        return [
            next(iter(matches.values()))["player_name"]
            for matches in _player_match_history.values()
            if matches
        ]


def clear_player_history(player_name: Optional[str] = None) -> None:
    """Clear player history. If player_name given, clear only that player."""
    with _history_lock:
        if player_name:
            key = player_name.lower().strip()
            _player_match_history.pop(key, None)
        else:
            _player_match_history.clear()
