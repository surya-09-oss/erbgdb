"""IPL API aggregator - fetches realtime data from Cricbuzz."""

from app.scrapers.cricbuzz import (
    IPL_SQUAD_MAP,
    fetch_ipl_live_scores_from_cricbuzz,
    fetch_ipl_points_table_from_cricbuzz,
    fetch_ipl_schedule_from_cricbuzz,
    fetch_ipl_squad_from_cricbuzz,
)

TEAM_CODES = {code: info["name"] for code, info in IPL_SQUAD_MAP.items()}

# Historical IPL winners data (static, does not change)
IPL_WINNERS = [
    {"year": 2008, "winner": "Rajasthan Royals", "runner_up": "Chennai Super Kings"},
    {"year": 2009, "winner": "Deccan Chargers", "runner_up": "Royal Challengers Bangalore"},
    {"year": 2010, "winner": "Chennai Super Kings", "runner_up": "Mumbai Indians"},
    {"year": 2011, "winner": "Chennai Super Kings", "runner_up": "Royal Challengers Bangalore"},
    {"year": 2012, "winner": "Kolkata Knight Riders", "runner_up": "Chennai Super Kings"},
    {"year": 2013, "winner": "Mumbai Indians", "runner_up": "Chennai Super Kings"},
    {"year": 2014, "winner": "Kolkata Knight Riders", "runner_up": "Kings XI Punjab"},
    {"year": 2015, "winner": "Mumbai Indians", "runner_up": "Chennai Super Kings"},
    {"year": 2016, "winner": "Sunrisers Hyderabad", "runner_up": "Royal Challengers Bangalore"},
    {"year": 2017, "winner": "Mumbai Indians", "runner_up": "Rising Pune Supergiant"},
    {"year": 2018, "winner": "Chennai Super Kings", "runner_up": "Sunrisers Hyderabad"},
    {"year": 2019, "winner": "Mumbai Indians", "runner_up": "Chennai Super Kings"},
    {"year": 2020, "winner": "Mumbai Indians", "runner_up": "Delhi Capitals"},
    {"year": 2021, "winner": "Chennai Super Kings", "runner_up": "Kolkata Knight Riders"},
    {"year": 2022, "winner": "Gujarat Titans", "runner_up": "Rajasthan Royals"},
    {"year": 2023, "winner": "Chennai Super Kings", "runner_up": "Gujarat Titans"},
    {"year": 2024, "winner": "Kolkata Knight Riders", "runner_up": "Sunrisers Hyderabad"},
    {"year": 2025, "winner": "Royal Challengers Bengaluru", "runner_up": "Punjab Kings"},
]


async def fetch_ipl_schedule() -> dict:
    return await fetch_ipl_schedule_from_cricbuzz()


async def fetch_ipl_points_table() -> dict:
    return await fetch_ipl_points_table_from_cricbuzz()


async def fetch_ipl_live_scores() -> dict:
    return await fetch_ipl_live_scores_from_cricbuzz()


async def fetch_ipl_squad(team_code: str) -> dict:
    return await fetch_ipl_squad_from_cricbuzz(team_code)


async def fetch_ipl_winners() -> dict:
    return {"winners": IPL_WINNERS, "total": len(IPL_WINNERS)}
