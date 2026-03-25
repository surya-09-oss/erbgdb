"""International matches API — dynamically discovers and fetches live data for
all non-IPL international matches from Cricbuzz."""

import logging

from app.scrapers.cricbuzz import (
    fetch_live_matches,
    fetch_match_score,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dynamic international match discovery cache
# ---------------------------------------------------------------------------
# These are populated at runtime from the Cricbuzz live-scores page so new
# matches are picked up automatically without code changes.
INTERNATIONAL_MATCHES: dict[str, dict] = {}
INTERNATIONAL_TEAM_CODES: dict[str, str] = {}

# Match types we consider "international" (from Cricbuzz typeMatches)
_INTERNATIONAL_MATCH_TYPES = {"International", "Women"}


async def discover_international_matches() -> list[dict]:
    """Discover all currently live/recent international matches from Cricbuzz
    and update the module-level registries."""
    all_matches = await fetch_live_matches()
    discovered: list[dict] = []

    for match in all_matches:
        match_type = match.get("match_type", "")
        if match_type not in _INTERNATIONAL_MATCH_TYPES:
            continue

        match_id = str(match.get("match_id", ""))
        if not match_id:
            continue

        teams = match.get("teams", [])
        team1 = teams[0] if len(teams) > 0 else {}
        team2 = teams[1] if len(teams) > 1 else {}

        entry = {
            "match_id": match_id,
            "title": match.get("title", ""),
            "short_title": f"{team1.get('short_name', '')} vs {team2.get('short_name', '')}",
            "team1": team1,
            "team2": team2,
            "series": match.get("series", ""),
            "match_type": match_type,
            "match_format": match.get("match_format", ""),
            "state": match.get("state", ""),
            "status": match.get("status", ""),
        }

        # Update the module-level registry
        INTERNATIONAL_MATCHES[match_id] = entry
        discovered.append(entry)

        # Update team codes
        for team in [team1, team2]:
            short = team.get("short_name", "").lower()
            name = team.get("name", "")
            if short and name:
                INTERNATIONAL_TEAM_CODES[short] = name

    return discovered


async def fetch_international_live_scores() -> dict:
    """Fetch live scores for all international matches.

    Dynamically discovers matches from Cricbuzz live-scores page, so new
    matches appear automatically without code changes.
    """
    all_matches = await fetch_live_matches()
    results: list[dict] = []

    for match in all_matches:
        match_type = match.get("match_type", "")
        if match_type not in _INTERNATIONAL_MATCH_TYPES:
            continue
        results.append(match)

        # Keep the registry up to date
        match_id = str(match.get("match_id", ""))
        if match_id:
            teams = match.get("teams", [])
            team1 = teams[0] if len(teams) > 0 else {}
            team2 = teams[1] if len(teams) > 1 else {}
            INTERNATIONAL_MATCHES[match_id] = {
                "match_id": match_id,
                "title": match.get("title", ""),
                "short_title": f"{team1.get('short_name', '')} vs {team2.get('short_name', '')}",
                "team1": team1,
                "team2": team2,
                "series": match.get("series", ""),
                "match_type": match_type,
                "match_format": match.get("match_format", ""),
                "state": match.get("state", ""),
                "status": match.get("status", ""),
            }

    return {
        "series": "International Matches",
        "matches": results,
        "total": len(results),
    }


async def fetch_international_match_score(match_id: str) -> dict:
    """Fetch detailed live score for a specific international match.

    Works for any valid Cricbuzz match ID — does not require pre-registration.
    """
    score_data = await fetch_match_score(match_id)

    if not score_data or "error" in score_data:
        return score_data or {"error": "Failed to fetch match data", "match_id": match_id}

    return score_data


def get_international_matches() -> list[dict]:
    """Return all discovered international matches."""
    return list(INTERNATIONAL_MATCHES.values())
