"""International matches API — fetches live data for non-IPL matches like SA vs NZ."""

from app.scrapers.cricbuzz import (
    fetch_live_matches,
    fetch_match_score,
)

# Registered international matches: match_id -> match info
INTERNATIONAL_MATCHES: dict[str, dict] = {
    "122731": {
        "match_id": "122731",
        "title": "South Africa vs New Zealand",
        "short_title": "SA vs NZ",
        "team1": {"name": "South Africa", "short_name": "SA", "code": "sa"},
        "team2": {"name": "New Zealand", "short_name": "NZ", "code": "nz"},
        "series": "South Africa vs New Zealand 2026",
        "match_type": "International",
    },
}

# Team codes for international teams
INTERNATIONAL_TEAM_CODES: dict[str, str] = {
    "sa": "South Africa",
    "nz": "New Zealand",
}


async def fetch_international_live_scores() -> dict:
    """Fetch live scores for all registered international matches."""
    results: list[dict] = []

    # Try to find these matches in Cricbuzz live matches
    all_live = await fetch_live_matches()

    for match_id, match_info in INTERNATIONAL_MATCHES.items():
        # Check if this match is in live matches
        found = False
        for live_match in all_live:
            if str(live_match.get("match_id", "")) == match_id:
                results.append(live_match)
                found = True
                break

        if not found:
            # Fetch individual match score
            score_data = await fetch_match_score(match_id)
            if score_data and "error" not in score_data:
                results.append({
                    "match_id": match_id,
                    "title": score_data.get("title") or match_info["title"],
                    "series": match_info["series"],
                    "match_type": match_info["match_type"],
                    "status": score_data.get("status", ""),
                    "status_type": score_data.get("status_type", "upcoming"),
                    "live_score": score_data.get("live_score"),
                    "run_rate": score_data.get("run_rate"),
                    "match_date": score_data.get("match_date"),
                    "batters": score_data.get("batters", []),
                    "bowlers": score_data.get("bowlers", []),
                    "teams": [
                        match_info["team1"],
                        match_info["team2"],
                    ],
                })
            else:
                results.append({
                    "match_id": match_id,
                    "title": match_info["title"],
                    "series": match_info["series"],
                    "match_type": match_info["match_type"],
                    "status": score_data.get("status", "Data will update when match starts") if score_data else "Data will update when match starts",
                    "status_type": score_data.get("status_type", "upcoming") if score_data else "upcoming",
                    "teams": [
                        match_info["team1"],
                        match_info["team2"],
                    ],
                })

    return {
        "series": "International Matches",
        "matches": results,
        "total": len(results),
    }


async def fetch_international_match_score(match_id: str) -> dict:
    """Fetch detailed live score for a specific international match."""
    if match_id not in INTERNATIONAL_MATCHES:
        return {
            "error": f"Match ID '{match_id}' is not a registered international match",
            "registered_matches": list(INTERNATIONAL_MATCHES.keys()),
        }

    score_data = await fetch_match_score(match_id)
    match_info = INTERNATIONAL_MATCHES[match_id]

    if score_data and "error" not in score_data:
        score_data["series"] = match_info["series"]
        score_data["match_type"] = match_info["match_type"]
        score_data["teams"] = [match_info["team1"], match_info["team2"]]

    return score_data


def get_international_matches() -> list[dict]:
    """Return all registered international matches."""
    return list(INTERNATIONAL_MATCHES.values())
