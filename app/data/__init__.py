"""Player data management — loads from embedded JSON, supports runtime admin edits."""

import json
import threading
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).parent
_PLAYERS_FILE = _DATA_DIR / "players.json"

_lock = threading.Lock()

# In-memory player store: { team_code: [ {name, role, team, ...}, ... ] }
_players: dict[str, list[dict]] = {}


def _load() -> None:
    """Load players from the JSON file into memory."""
    global _players
    with open(_PLAYERS_FILE, "r") as f:
        _players = json.load(f)


def _save() -> None:
    """Persist current in-memory player data back to JSON."""
    with open(_PLAYERS_FILE, "w") as f:
        json.dump(_players, f, indent=2)


def get_all_players() -> dict[str, list[dict]]:
    """Return all players grouped by team code."""
    with _lock:
        if not _players:
            _load()
        return _players


def get_team_players(team_code: str) -> list[dict]:
    """Return players for a specific team."""
    all_p = get_all_players()
    return all_p.get(team_code.lower(), [])


def get_players_by_role(role: str) -> list[dict]:
    """Return all players matching a given role across all teams."""
    all_p = get_all_players()
    result: list[dict] = []
    for players in all_p.values():
        for p in players:
            if p.get("role", "").lower() == role.lower():
                result.append(p)
    return result


def find_player(name: str, team_code: Optional[str] = None) -> Optional[dict]:
    """Find a player by name, optionally filtered by team."""
    all_p = get_all_players()
    name_lower = name.lower().strip()
    teams = [team_code.lower()] if team_code else list(all_p.keys())
    for tc in teams:
        for p in all_p.get(tc, []):
            if p["name"].lower().strip() == name_lower:
                return p
    return None


def add_player(player: dict) -> bool:
    """Add a player to a team. Returns True on success."""
    with _lock:
        if not _players:
            _load()
        team_code = player.get("team", "").lower()
        if team_code not in _players:
            _players[team_code] = []
        # Check for duplicate
        for existing in _players[team_code]:
            if existing["name"].lower() == player["name"].lower():
                return False
        _players[team_code].append(player)
        _save()
        return True


def remove_player(name: str, team_code: str) -> bool:
    """Remove a player from a team. Returns True if removed."""
    with _lock:
        if not _players:
            _load()
        team_code = team_code.lower()
        if team_code not in _players:
            return False
        name_lower = name.lower().strip()
        original_len = len(_players[team_code])
        _players[team_code] = [
            p for p in _players[team_code]
            if p["name"].lower().strip() != name_lower
        ]
        if len(_players[team_code]) < original_len:
            _save()
            return True
        return False


def get_all_players_flat() -> list[dict]:
    """Return a flat list of all players across all teams."""
    all_p = get_all_players()
    result: list[dict] = []
    for players in all_p.values():
        result.extend(players)
    return result
