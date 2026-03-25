import asyncio
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
from app.scrapers.international_api import (
    INTERNATIONAL_MATCHES,
    INTERNATIONAL_TEAM_CODES,
    discover_international_matches,
    fetch_international_live_scores,
    fetch_international_match_score,
    get_international_matches,
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
from app.fantasy.scorecard import fetch_full_scorecard
from app.fantasy.player_history import (
    get_player_all_matches,
    get_player_match_points,
    get_player_cumulative_total,
    get_team_match_history,
)

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

# ---------------------------------------------------------------------------
# Auto-update configuration
# ---------------------------------------------------------------------------
_auto_update_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

# Live states that should trigger fantasy-point refresh
_LIVE_STATES = {"In Progress", "Toss", "Stumps", "Lunch", "Tea", "Innings Break", "Drink", "Complete"}


async def _discover_live_match_ids() -> list[str]:
    """Dynamically discover all live/in-progress match IDs from Cricbuzz.

    Fetches the live-scores page and returns match IDs for matches that are
    currently in progress, at toss, or recently completed — covering both
    IPL and international matches automatically.
    """
    from app.scrapers.cricbuzz import fetch_live_matches

    try:
        all_matches = await fetch_live_matches()
    except Exception:
        logger.exception("Failed to discover live matches for auto-update")
        return list(INTERNATIONAL_MATCHES.keys())

    live_ids: list[str] = []
    for match in all_matches:
        state = match.get("state", "")
        if state in _LIVE_STATES:
            mid = str(match.get("match_id", ""))
            if mid:
                live_ids.append(mid)

    # Also include any previously discovered international matches
    for mid in INTERNATIONAL_MATCHES:
        if mid not in live_ids:
            live_ids.append(mid)

    return live_ids


async def _auto_update_fantasy_points() -> None:
    """Background task that refreshes fantasy points for all live matches every 30s.

    Dynamically discovers live match IDs from Cricbuzz on each cycle, so new
    matches are picked up automatically without code changes or restarts.
    """
    while True:
        try:
            # Discover international matches to keep registry fresh
            await discover_international_matches()

            # Get all live match IDs dynamically
            live_ids = await _discover_live_match_ids()
            logger.info("Auto-update: discovered %d live matches: %s", len(live_ids), live_ids)

            for match_id in live_ids:
                try:
                    await process_match(match_id, force_refresh=True)
                    logger.info("Auto-updated fantasy points for match %s", match_id)
                except Exception:
                    logger.exception("Auto-update failed for match %s", match_id)
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Auto-update loop error")
            await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    global _auto_update_task
    logger.info("Admin token configured (length=%d)", len(ADMIN_TOKEN))
    _auto_update_task = asyncio.create_task(_auto_update_fantasy_points())
    logger.info("Fantasy points auto-update task started (every 30s)")
    yield
    if _auto_update_task:
        _auto_update_task.cancel()
        try:
            await _auto_update_task
        except asyncio.CancelledError:
            pass
    await cache.clear()


app = FastAPI(
    title="Cricket Fantasy API",
    description="Free, unlimited, self-hosted JSON API for IPL 2026 & International cricket data with Fantasy Points system.",
    version="3.0.0",
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


# ===========================================================================
# IPL 2026 endpoints
# ===========================================================================
@app.get("/api/ipl/live-scores")
async def ipl_live_scores() -> dict:
    """Get live scores for IPL 2026 matches only."""
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


# ===========================================================================
# International Cricket endpoints (SA vs NZ, etc.)
# ===========================================================================
@app.get("/api/international/live-scores")
async def international_live_scores() -> dict:
    """Get live scores for registered international matches (e.g. SA vs NZ)."""
    return await _cached_response(
        "international_live_scores", fetch_international_live_scores
    )


@app.get("/api/international/matches")
async def international_matches_list() -> dict:
    """List all registered international matches."""
    matches = get_international_matches()
    return {
        "status": "success",
        "matches": matches,
        "total": len(matches),
    }


@app.get("/api/international/match/{match_id}")
async def international_match_detail(match_id: str) -> dict:
    """Get detailed live score for a specific international match."""
    return await _cached_response(
        f"intl_match_{match_id}",
        lambda: fetch_international_match_score(match_id),
    )


@app.get("/api/international/teams")
async def international_teams() -> dict:
    """Get all international team codes."""
    return {
        "status": "success",
        "count": len(INTERNATIONAL_TEAM_CODES),
        "teams": INTERNATIONAL_TEAM_CODES,
    }


# ===========================================================================
# Fantasy Players endpoints (works for both IPL and International teams)
# ===========================================================================
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
    """Get all fantasy players for a specific team (IPL or international)."""
    players = get_team_players(team_code)
    all_codes = {**TEAM_CODES, **INTERNATIONAL_TEAM_CODES}
    if not players:
        return {
            "status": "error",
            "error": f"No players found for team '{team_code}' or invalid team code",
            "valid_codes": list(all_codes.keys()),
        }
    return {
        "status": "success",
        "team": team_code.lower(),
        "team_name": all_codes.get(team_code.lower(), team_code),
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


# ===========================================================================
# Fantasy Points endpoints (works for both IPL and International matches)
# ===========================================================================
@app.get("/api/fantasy/points/{match_id}")
async def fantasy_match_points(
    match_id: str,
    refresh: bool = Query(False, description="Force refresh from Cricbuzz"),
) -> dict:
    """Get fantasy points for all players in a match (IPL or International).
    Points are auto-calculated from live Cricbuzz scorecard data.
    Auto-updates every 30 seconds for tracked matches.
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
            "available_matches": {
                "ipl_example": "149618",
                "international": list(INTERNATIONAL_MATCHES.keys()),
            },
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
                "boundary_4": "+4 bonus per four (total +5 per four: 1 run + 4 bonus)",
                "six": "+7 bonus per six (total +8 per six: 1 run + 7 bonus)",
                "milestones": {
                    "25_runs": "+4 bonus",
                    "50_runs": "+8 bonus (cumulative with 25-run bonus)",
                    "75_runs": "+12 bonus (cumulative with 25 & 50 bonuses)",
                    "100_runs": "+16 bonus (cumulative with all lower milestones)",
                },
                "duck": "-2 points (batters/WK/all-rounders only)",
                "strike_rate": {
                    "above_170": "+6",
                    "150_to_170": "+4",
                    "130_to_150": "+2",
                    "60_to_70": "-2",
                    "50_to_60": "-4",
                    "below_50": "-6",
                    "note": "Only applies if >= 10 balls faced",
                },
                "example": "50 runs with 5 fours = 50 (runs) + 20 (5×4 boundary bonus) + 8 (50-run milestone) = 78 points",
            },
            "bowling": {
                "wicket": "+25 points per wicket",
                "lbw_or_bowled_bonus": "+8 per LBW/Bowled dismissal (total +33 per LBW/Bowled wicket)",
                "three_wickets": "+4 bonus",
                "four_wickets": "+8 bonus",
                "five_wickets": "+16 bonus",
                "maiden_over": "+12 points per maiden",
                "economy_rate": {
                    "below_5": "+6",
                    "5_to_6": "+4",
                    "6_to_7": "+2",
                    "9_to_10": "-2",
                    "10_to_11": "-4",
                    "above_11": "-6",
                    "note": "Only applies if >= 2 overs bowled",
                },
            },
            "fielding": {
                "catch": "+8 points per catch",
                "three_catches": "+28 total (24 catch points + 4 bonus)",
                "stumping": "+12 points per stumping",
                "run_out_direct": "+12 points per direct hit",
                "run_out_assist": "+6 points per assist",
            },
            "extra": {
                "playing_xi": "+4 points for being in Playing XI",
                "duck": "-2 points",
            },
            "applies_to": "Both IPL and International matches use the same scoring rules",
        },
    }


# ===========================================================================
# Fantasy Scorecard endpoint (raw scorecard + points, separate from live scores)
# ===========================================================================
@app.get("/api/fantasy/scorecard/{match_id}")
async def fantasy_scorecard(
    match_id: str,
    refresh: bool = Query(False, description="Force refresh from Cricbuzz"),
) -> dict:
    """Get the detailed fantasy scorecard for a match.
    Returns raw innings data (batting, bowling, fielding) plus calculated fantasy points.
    Works for both IPL and International matches.
    """
    cache_key = f"fantasy_scorecard_{match_id}"
    if not refresh:
        cached = await cache.get(cache_key)
        if cached is not None:
            return {
                "status": "success",
                "cached": True,
                "data": cached,
            }

    scorecard = await fetch_full_scorecard(match_id)
    points_result = await process_match(match_id, force_refresh=refresh)

    result = {
        "match_id": match_id,
        "scorecard": {
            "innings": scorecard.get("innings", []),
            "fielding": scorecard.get("fielding", {}),
        },
        "fantasy_points": points_result.get("players", []) if "error" not in points_result else [],
        "total_players": points_result.get("total_players", 0) if "error" not in points_result else 0,
    }

    sc_err = scorecard.get("error")
    pt_err = points_result.get("error")
    if sc_err or pt_err:
        result["error"] = sc_err or pt_err
    else:
        await cache.set(cache_key, result)

    return {
        "status": "success" if "error" not in result else "error",
        "cached": False,
        "data": result,
    }


# ===========================================================================
# Player Match-Wise Points endpoints
# ===========================================================================
@app.get("/api/fantasy/player/{player_name}/matches")
async def fantasy_player_match_history(player_name: str) -> dict:
    """Get all match-wise fantasy points for a specific player.

    Each match entry has independent points (starting from 0).
    Old match data is always preserved.
    """
    matches = get_player_all_matches(player_name)
    if not matches:
        return {
            "status": "success",
            "player": player_name,
            "message": "No match data found. Process matches first via /api/fantasy/points/{match_id}",
            "matches": [],
            "total_matches": 0,
        }
    return {
        "status": "success",
        "player": matches[0].get("player_name", player_name),
        "team": matches[0].get("team", "unknown"),
        "role": matches[0].get("role", "Unknown"),
        "image_url": matches[0].get("image_url"),
        "matches": matches,
        "total_matches": len(matches),
    }


@app.get("/api/fantasy/player/{player_name}/match/{match_id}")
async def fantasy_player_single_match(
    player_name: str,
    match_id: str,
) -> dict:
    """Get a player's fantasy points for a specific match.

    Points for each match are independent and start from 0.
    """
    entry = get_player_match_points(player_name, match_id)
    if not entry:
        return {
            "status": "error",
            "error": f"No data for player '{player_name}' in match '{match_id}'. "
                     f"Process the match first via /api/fantasy/points/{match_id}",
        }
    return {
        "status": "success",
        "data": entry,
    }


@app.get("/api/fantasy/player/{player_name}/total")
async def fantasy_player_cumulative(player_name: str) -> dict:
    """Get cumulative total fantasy points for a player across all matches.

    Shows per-match breakdown plus overall totals.
    """
    summary = get_player_cumulative_total(player_name)
    return {
        "status": "success",
        "data": summary,
    }


@app.get("/api/fantasy/team/{team_code}/match-history")
async def fantasy_team_match_history(team_code: str) -> dict:
    """Get match-wise fantasy points for all players in a team.

    Returns every recorded match entry for players belonging to this team.
    """
    entries = get_team_match_history(team_code)
    if not entries:
        return {
            "status": "success",
            "team": team_code.lower(),
            "message": "No match history found. Process matches first via /api/fantasy/points/{match_id}",
            "players": [],
            "total_entries": 0,
        }

    # Group by player for a cleaner response
    player_map: dict[str, list[dict]] = {}
    for entry in entries:
        pname = entry.get("player_name", "Unknown")
        if pname not in player_map:
            player_map[pname] = []
        player_map[pname].append({
            "match_id": entry["match_id"],
            "fantasy_points": entry["fantasy_points"],
            "batting_stats": entry.get("batting_stats"),
            "bowling_stats": entry.get("bowling_stats"),
            "fielding_stats": entry.get("fielding_stats"),
        })

    players_list = []
    for pname, match_entries in player_map.items():
        first = next(e for e in entries if e.get("player_name") == pname)
        players_list.append({
            "player_name": pname,
            "role": first.get("role", "Unknown"),
            "image_url": first.get("image_url"),
            "matches": match_entries,
            "total_matches": len(match_entries),
        })

    return {
        "status": "success",
        "team": team_code.lower(),
        "players": players_list,
        "total_players": len(players_list),
    }


# ===========================================================================
# Auto-Update Status endpoint
# ===========================================================================
@app.get("/api/fantasy/auto-update-status")
async def fantasy_auto_update_status() -> dict:
    """Check the status of the auto-update background task."""
    tracked = list(INTERNATIONAL_MATCHES.keys())
    return {
        "status": "success",
        "auto_update": {
            "enabled": True,
            "interval_seconds": 30,
            "mode": "dynamic",
            "description": "Automatically discovers all live IPL and international matches from Cricbuzz",
            "known_international_matches": tracked,
            "total_known_international": len(tracked),
            "task_running": _auto_update_task is not None and not _auto_update_task.done(),
        },
    }


# ===========================================================================
# Admin API endpoints (requires ADMIN_TOKEN)
# ===========================================================================
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
