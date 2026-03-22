from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from app.scrapers.cache import cache
from app.scrapers.ipl_api import (
    TEAM_CODES,
    fetch_ipl_live_scores,
    fetch_ipl_points_table,
    fetch_ipl_schedule,
    fetch_ipl_squad,
    fetch_ipl_winners,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    yield
    await cache.clear()


app = FastAPI(
    title="IPL 2026 API",
    description="Free, unlimited, self-hosted JSON API for IPL 2026 data.",
    version="1.0.0",
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
# IPL 2026 endpoints
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
