import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Coroutine, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from app.scrapers.cache import cache
from app.scrapers.ipl_api import (
    TEAM_CODES,
    fetch_ipl_live_scores,
    fetch_ipl_points_table,
    fetch_ipl_schedule,
    fetch_ipl_squad,
    fetch_ipl_winners,
)
from app.data import (
    add_player,
    get_all_players,
    get_all_players_flat,
    get_players_by_role,
    get_team_players,
    remove_player,
)
from app.fantasy.admin import ADMIN_TOKEN, verify_admin_token
from app.fantasy.match_processor import clear_match_cache, process_match

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Admin token configured (length=%d)", len(ADMIN_TOKEN))
    yield
    await cache.clear()


app = FastAPI(
    title="IPL 2026 Fantasy API",
    description="Free, unlimited, self-hosted JSON API for IPL 2026 data with Fantasy Points system.",
    version="2.0.0",
    lifespan=lifespan,
)

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


# ---------------------------------------------------------------------------
# Pydantic models for admin API
# ---------------------------------------------------------------------------
class AddPlayerRequest(BaseModel):
    name: str
    role: str  # Batsman, Bowler, All Rounder, Wicket Keeper
    team: str  # team code: csk, mi, rcb, etc.
    base_price_cr: Optional[float] = None
    sold_price_cr: Optional[float] = None
    overseas: bool = False
    retained: bool = False
    image_url: Optional[str] = None


class RemovePlayerRequest(BaseModel):
    name: str
    team: str  # team code


# ---------------------------------------------------------------------------
# Documentation page
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def docs_page(request: Request) -> HTMLResponse:
    base_url = str(request.base_url).rstrip("/")
    template = jinja_env.get_template("docs.html")
    html = template.render(base_url=base_url)
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Admin Panel page
# ---------------------------------------------------------------------------
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    base_url = str(request.base_url).rstrip("/")
    template = jinja_env.get_template("admin.html")
    html = template.render(base_url=base_url)
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


async def _cached_response(
    cache_key: str,
    fetcher: Callable[[], Coroutine[Any, Any, dict]],
) -> dict:
    """Fetch data with caching. Only successful responses are cached."""
    cached = await cache.get(cache_key)
    if cached is not None:
        return {
            "status": "success",
            "cached": True,
            "cache_ttl_seconds": 10,
            "data": cached,
        }

    try:
        data = await fetcher()
    except Exception as exc:
        logger.exception("Fetcher failed for %s", cache_key)
        return {
            "status": "error",
            "cached": False,
            "cache_ttl_seconds": 10,
            "data": {"error": str(exc)},
        }

    has_error = isinstance(data, dict) and "error" in data
    if not has_error:
        await cache.set(cache_key, data)
    return {
        "status": "success" if not has_error else "error",
        "cached": False,
        "cache_ttl_seconds": 10,
        "data": data,
    }


# ---------------------------------------------------------------------------
# IPL 2026 endpoints (existing)
# ---------------------------------------------------------------------------
@app.get("/api/ipl/live-scores")
async def ipl_live_scores() -> dict:
    return await _cached_response("ipl_live_scores", fetch_ipl_live_scores)


@app.get("/api/ipl/schedule")
async def ipl_schedule() -> dict:
    return await _cached_response("ipl_schedule", fetch_ipl_schedule)


@app.get("/api/ipl/points-table")
async def ipl_points_table() -> dict:
    return await _cached_response("ipl_points_table", fetch_ipl_points_table)


@app.get("/api/ipl/squad/{team_code}")
async def ipl_squad(team_code: str) -> dict:
    return await _cached_response(
        f"ipl_squad_{team_code.lower()}",
        lambda: fetch_ipl_squad(team_code),
    )


@app.get("/api/ipl/winners")
async def ipl_winners() -> dict:
    return await _cached_response("ipl_winners", fetch_ipl_winners)


@app.get("/api/ipl/teams")
async def ipl_teams() -> dict:
    return {
        "status": "success",
        "count": len(TEAM_CODES),
        "teams": TEAM_CODES,
    }


# ---------------------------------------------------------------------------
# Fantasy Players endpoints
# ---------------------------------------------------------------------------
@app.get("/api/fantasy/players")
async def fantasy_all_players(
    team: Optional[str] = Query(None, description="Filter by team code"),
    role: Optional[str] = Query(None, description="Filter by role"),
) -> dict:
    """Get all fantasy players, optionally filtered by team or role."""
    if team:
        players = get_team_players(team)
        if role:
            players = [p for p in players if p.get("role", "").lower() == role.lower()]
        return {
            "status": "success",
            "team": team.lower(),
            "players": players,
            "total": len(players),
        }
    elif role:
        players = get_players_by_role(role)
        return {
            "status": "success",
            "role": role,
            "players": players,
            "total": len(players),
        }
    else:
        all_p = get_all_players()
        total = sum(len(v) for v in all_p.values())
        return {
            "status": "success",
            "teams": all_p,
            "total": total,
        }


@app.get("/api/fantasy/players/{team_code}")
async def fantasy_team_players(team_code: str) -> dict:
    """Get all fantasy players for a specific team."""
    players = get_team_players(team_code)
    if not players:
        return {
            "status": "error",
            "error": f"No players found for team '{team_code}' or invalid team code",
            "valid_codes": list(TEAM_CODES.keys()),
        }
    return {
        "status": "success",
        "team": team_code.lower(),
        "team_name": TEAM_CODES.get(team_code.lower(), team_code),
        "players": players,
        "total": len(players),
    }


@app.get("/api/fantasy/players/{team_code}/{player_role}")
async def fantasy_team_role_players(team_code: str, player_role: str) -> dict:
    """Get players of a specific role from a team.
    Roles: batsman, bowler, all_rounder, wicket_keeper
    """
    players = get_team_players(team_code)
    role_map = {
        "batsman": "Batsman",
        "batter": "Batsman",
        "bowler": "Bowler",
        "all_rounder": "All Rounder",
        "allrounder": "All Rounder",
        "all-rounder": "All Rounder",
        "wicket_keeper": "Wicket Keeper",
        "wicketkeeper": "Wicket Keeper",
        "wk": "Wicket Keeper",
    }
    normalized_role = role_map.get(player_role.lower(), player_role)
    filtered = [p for p in players if p.get("role", "").lower() == normalized_role.lower()]

    return {
        "status": "success",
        "team": team_code.lower(),
        "role": normalized_role,
        "players": filtered,
        "total": len(filtered),
    }


# ---------------------------------------------------------------------------
# Fantasy Points endpoints
# ---------------------------------------------------------------------------
@app.get("/api/fantasy/points/{match_id}")
async def fantasy_match_points(
    match_id: str,
    refresh: bool = Query(False, description="Force refresh from Cricbuzz"),
) -> dict:
    """Get fantasy points for all players in a specific match.
    Points are auto-calculated from live Cricbuzz scorecard data.
    """
    result = await process_match(match_id, force_refresh=refresh)
    return {
        "status": "success" if "error" not in result else "error",
        "cached": not refresh,
        "data": result,
    }


@app.get("/api/fantasy/points/{match_id}/{team_code}")
async def fantasy_match_team_points(
    match_id: str,
    team_code: str,
    refresh: bool = Query(False, description="Force refresh from Cricbuzz"),
) -> dict:
    """Get fantasy points for a specific team's players in a match."""
    result = await process_match(match_id, force_refresh=refresh)
    if "error" in result:
        return {"status": "error", "data": result}

    team_players = [
        p for p in result.get("players", [])
        if p.get("team", "").lower() == team_code.lower()
    ]

    return {
        "status": "success",
        "match_id": match_id,
        "team": team_code.lower(),
        "players": team_players,
        "total": len(team_players),
    }


@app.get("/api/fantasy/leaderboard")
async def fantasy_leaderboard(
    match_id: Optional[str] = Query(None, description="Match ID to get leaderboard for"),
) -> dict:
    """Get fantasy points leaderboard for a specific match."""
    if not match_id:
        return {
            "status": "success",
            "message": "Provide a match_id query parameter to get the leaderboard for a specific match.",
            "example": "/api/fantasy/leaderboard?match_id=149618",
        }

    result = await process_match(match_id)
    if "error" in result:
        return {"status": "error", "data": result}

    players = result.get("players", [])
    return {
        "status": "success",
        "match_id": match_id,
        "leaderboard": players[:50],
        "total_players": len(players),
    }


@app.get("/api/fantasy/scoring-rules")
async def fantasy_scoring_rules() -> dict:
    """Return the complete fantasy scoring rules."""
    return {
        "status": "success",
        "rules": {
            "batting": {
                "run_scored": "+1 point per run",
                "boundary_4": "+1 bonus per four",
                "six": "+2 bonus per six",
                "half_century": "+8 bonus (50 runs)",
                "century": "+16 bonus (100 runs)",
                "duck": "-2 points (batters/WK/all-rounders only)",
                "strike_rate": {
                    "above_170": "+6",
                    "150_to_170": "+4",
                    "130_to_150": "+2",
                    "below_60": "-6",
                    "note": "Only applies if >= 10 balls faced",
                },
            },
            "bowling": {
                "wicket": "+25 points per wicket",
                "lbw_or_bowled_bonus": "+8 per LBW/Bowled dismissal",
                "three_wickets": "+4 bonus",
                "four_wickets": "+8 bonus",
                "five_wickets": "+16 bonus",
                "maiden_over": "+12 points per maiden",
                "economy_rate": {
                    "below_5": "+6",
                    "5_to_6": "+4",
                    "6_to_7": "+2",
                    "above_12": "-6",
                    "note": "Only applies if >= 2 overs bowled",
                },
            },
            "fielding": {
                "catch": "+8 points per catch",
                "three_catches_bonus": "+4 bonus",
                "stumping": "+12 points per stumping",
                "run_out_direct": "+12 points per direct hit",
                "run_out_assist": "+6 points per assist",
            },
        },
    }


# ---------------------------------------------------------------------------
# Admin API endpoints (requires ADMIN_TOKEN)
# ---------------------------------------------------------------------------
def _check_admin(authorization: Optional[str]) -> None:
    """Verify admin authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header. Use: Bearer <admin_token>")
    token = authorization.replace("Bearer ", "").strip()
    if not verify_admin_token(token):
        raise HTTPException(status_code=403, detail="Invalid admin token")


@app.post("/api/admin/players/add")
async def admin_add_player(
    body: AddPlayerRequest,
    authorization: Optional[str] = Header(None),
) -> dict:
    """Add a new player to a team. Requires admin token."""
    _check_admin(authorization)

    player_data = {
        "name": body.name,
        "role": body.role,
        "team": body.team.lower(),
        "base_price_cr": body.base_price_cr,
        "sold_price_cr": body.sold_price_cr,
        "overseas": body.overseas,
        "retained": body.retained,
        "image_url": body.image_url,
    }

    success = add_player(player_data)
    if not success:
        return {
            "status": "error",
            "error": f"Player '{body.name}' already exists in team '{body.team}'",
        }

    return {
        "status": "success",
        "message": f"Player '{body.name}' added to team '{body.team}'",
        "player": player_data,
    }


@app.post("/api/admin/players/remove")
async def admin_remove_player(
    body: RemovePlayerRequest,
    authorization: Optional[str] = Header(None),
) -> dict:
    """Remove a player from a team. Requires admin token."""
    _check_admin(authorization)

    success = remove_player(body.name, body.team)
    if not success:
        return {
            "status": "error",
            "error": f"Player '{body.name}' not found in team '{body.team}'",
        }

    return {
        "status": "success",
        "message": f"Player '{body.name}' removed from team '{body.team}'",
    }


@app.post("/api/admin/cache/clear")
async def admin_clear_cache(
    match_id: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
) -> dict:
    """Clear fantasy points cache. Optionally specify match_id."""
    _check_admin(authorization)

    clear_match_cache(match_id)
    await cache.clear()

    return {
        "status": "success",
        "message": "Cache cleared" + (f" for match {match_id}" if match_id else " (all)"),
    }


@app.get("/api/admin/token")
async def admin_get_token(
    authorization: Optional[str] = Header(None),
) -> dict:
    """Verify admin token validity."""
    _check_admin(authorization)
    return {"status": "success", "message": "Token is valid"}
