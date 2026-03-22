"""IPL API aggregator - fetches data from the free IPL 2025 API on Render."""

import httpx

IPL_BASE_URL = "https://ipl-okn0.onrender.com"

TEAM_CODES = {
    "mi": "Mumbai Indians",
    "rcb": "Royal Challengers Bengaluru",
    "csk": "Chennai Super Kings",
    "dc": "Delhi Capitals",
    "pk": "Punjab Kings",
    "kkr": "Kolkata Knight Riders",
    "rr": "Rajasthan Royals",
    "srh": "Sunrisers Hyderabad",
    "gt": "Gujarat Titans",
    "lsg": "Lucknow Super Giants",
}


async def _fetch(endpoint: str) -> dict:
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            r = await client.get(f"{IPL_BASE_URL}{endpoint}")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError:
            return {"error": f"Failed to fetch {endpoint}", "status_code": 503}
        except Exception:
            return {"error": f"Invalid response from {endpoint}", "status_code": 502}


async def fetch_ipl_schedule() -> dict:
    return await _fetch("/ipl-2025-schedule")


async def fetch_ipl_points_table() -> dict:
    return await _fetch("/ipl-2025-points-table")


async def fetch_ipl_live_scores() -> dict:
    return await _fetch("/ipl-2025-live-score-s3")


async def fetch_ipl_squad(team_code: str) -> dict:
    team_code = team_code.lower().strip()
    if team_code not in TEAM_CODES:
        return {
            "error": f"Invalid team code '{team_code}'",
            "valid_codes": TEAM_CODES,
            "status_code": 400,
        }
    return await _fetch(f"/squad/{team_code}")


async def fetch_ipl_winners() -> dict:
    return await _fetch("/ipl-winners")
