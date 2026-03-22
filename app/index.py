import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from app.scrapers.cache import cache
from app.scrapers.cricbuzz import fetch_live_matches, fetch_match_score
from app.scrapers.cricket_api_scraper import (
    fetch_score_flat,
    fetch_score_live,
    _not_found_flat,
    _not_found_live,
)
from app.scrapers.ipl_api import (
    TEAM_CODES,
    fetch_ipl_live_scores,
    fetch_ipl_points_table,
    fetch_ipl_schedule,
    fetch_ipl_squad,
    fetch_ipl_winners,
)

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


AUTO_UPDATE_INTERVAL = 10  # seconds


async def _auto_update_loop() -> None:
    """Background task that refreshes live match data every AUTO_UPDATE_INTERVAL seconds."""
    while True:
        try:
            data = await fetch_live_matches()
            if data:
                await cache.set("live_matches", data)
                logger.info("Auto-update: refreshed %d live matches", len(data))
        except Exception:
            logger.exception("Auto-update: failed to refresh live matches")
        await asyncio.sleep(AUTO_UPDATE_INTERVAL)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    task = asyncio.create_task(_auto_update_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await cache.clear()


app = FastAPI(
    title="Cricket API",
    description="Free, unlimited, self-hosted JSON API for live cricket scores and IPL data. "
    "Compatible with sanwebinfo/cricket-api format.",
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
# Documentation page
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def docs_page(request: Request) -> HTMLResponse:
    base_url = str(request.base_url).rstrip("/")
    template = jinja_env.get_template("docs.html")
    html = template.render(base_url=base_url)
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# General Cricket endpoints
# ---------------------------------------------------------------------------
@app.get("/api/live-matches")
async def live_matches() -> dict:
    cache_key = "live_matches"
    cached = await cache.get(cache_key)
    if cached is not None:
        return {
            "status": "success",
            "cached": True,
            "cache_ttl_seconds": 10,
            "count": len(cached),
            "matches": cached,
        }

    data = await fetch_live_matches()
    if data:  # don't cache empty list from a failed fetch
        await cache.set(cache_key, data)
    return {
        "status": "success",
        "cached": False,
        "cache_ttl_seconds": 10,
        "count": len(data),
        "matches": data,
    }


@app.get("/api/match-score")
async def match_score(
    id: str = Query(..., description="Match ID from Cricbuzz"),
) -> dict:
    cache_key = f"match_score_{id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return {
            "status": "success",
            "cached": True,
            "cache_ttl_seconds": 10,
            "data": cached,
        }

    data = await fetch_match_score(id)
    if "error" not in data:
        await cache.set(cache_key, data)
    return {
        "status": "success" if "error" not in data else "error",
        "cached": False,
        "cache_ttl_seconds": 10,
        "data": data,
    }


# ---------------------------------------------------------------------------
# IPL 2025 endpoints
# ---------------------------------------------------------------------------
@app.get("/api/ipl/live-scores")
async def ipl_live_scores() -> dict:
    cache_key = "ipl_live_scores"
    cached = await cache.get(cache_key)
    if cached is not None:
        return {
            "status": "success",
            "cached": True,
            "cache_ttl_seconds": 10,
            "data": cached,
        }

    data = await fetch_ipl_live_scores()
    if "error" not in data:
        await cache.set(cache_key, data)
    return {
        "status": "success" if "error" not in data else "error",
        "cached": False,
        "cache_ttl_seconds": 10,
        "data": data,
    }


@app.get("/api/ipl/schedule")
async def ipl_schedule() -> dict:
    cache_key = "ipl_schedule"
    cached = await cache.get(cache_key)
    if cached is not None:
        return {
            "status": "success",
            "cached": True,
            "cache_ttl_seconds": 10,
            "data": cached,
        }

    data = await fetch_ipl_schedule()
    if "error" not in data:
        await cache.set(cache_key, data)
    return {
        "status": "success" if "error" not in data else "error",
        "cached": False,
        "cache_ttl_seconds": 10,
        "data": data,
    }


@app.get("/api/ipl/points-table")
async def ipl_points_table() -> dict:
    cache_key = "ipl_points_table"
    cached = await cache.get(cache_key)
    if cached is not None:
        return {
            "status": "success",
            "cached": True,
            "cache_ttl_seconds": 10,
            "data": cached,
        }

    data = await fetch_ipl_points_table()
    if "error" not in data:
        await cache.set(cache_key, data)
    return {
        "status": "success" if "error" not in data else "error",
        "cached": False,
        "cache_ttl_seconds": 10,
        "data": data,
    }


@app.get("/api/ipl/squad/{team_code}")
async def ipl_squad(team_code: str) -> dict:
    cache_key = f"ipl_squad_{team_code.lower()}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return {
            "status": "success",
            "cached": True,
            "cache_ttl_seconds": 10,
            "data": cached,
        }

    data = await fetch_ipl_squad(team_code)
    if "error" not in data:
        await cache.set(cache_key, data)
    return {
        "status": "success" if "error" not in data else "error",
        "cached": False,
        "cache_ttl_seconds": 10,
        "data": data,
    }


@app.get("/api/ipl/winners")
async def ipl_winners() -> dict:
    cache_key = "ipl_winners"
    cached = await cache.get(cache_key)
    if cached is not None:
        return {
            "status": "success",
            "cached": True,
            "cache_ttl_seconds": 10,
            "data": cached,
        }

    data = await fetch_ipl_winners()
    if "error" not in data:
        await cache.set(cache_key, data)
    return {
        "status": "success" if "error" not in data else "error",
        "cached": False,
        "cache_ttl_seconds": 10,
        "data": data,
    }


@app.get("/api/ipl/teams")
async def ipl_teams() -> dict:
    return {
        "status": "success",
        "count": len(TEAM_CODES),
        "teams": TEAM_CODES,
    }


# ---------------------------------------------------------------------------
# Cricket-API compatible endpoints (sanwebinfo/cricket-api format)
# ---------------------------------------------------------------------------
@app.get("/score")
async def cricket_api_score(
    id: str = Query(None, description="Match ID from Cricbuzz"),
) -> dict:
    """Get match score in flat JSON format (cricket-api compatible).

    Same response structure as https://github.com/sanwebinfo/cricket-api /score endpoint.
    """
    if not id:
        return _not_found_flat()

    cache_key = f"cricket_api_score_{id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    data = await fetch_score_flat(id)
    if data.get("title") != "Data Not Found":
        await cache.set(cache_key, data)
    return data


@app.get("/score/live")
async def cricket_api_score_live(
    id: str = Query(None, description="Match ID from Cricbuzz"),
) -> dict:
    """Get match score in nested JSON format (cricket-api compatible).

    Same response structure as https://github.com/sanwebinfo/cricket-api /score/live endpoint.
    """
    if not id:
        return _not_found_live()

    cache_key = f"cricket_api_live_{id}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    data = await fetch_score_live(id)
    if data.get("livescore", {}).get("title") != "Data Not Found":
        await cache.set(cache_key, data)
    return data
