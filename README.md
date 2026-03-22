# IPL 2026 API

Free, unlimited, self-hosted JSON API for IPL 2026 data with 10-second auto-refresh cache.

## Features

- **Live Scores** — Real-time IPL 2026 match scores, auto-updated every 10 seconds
- **Full Schedule** — Complete match schedule with dates, venues, and teams
- **Points Table** — Current standings with NRR, wins, losses
- **Team Squads** — All 10 IPL team squads for 2026 season
- **Historical Winners** — Every IPL winner from 2008 to 2025
- **No API Key** — Free, unlimited, zero config
- **Self-Hosted** — Deploy anywhere (Docker, Render, Vercel, your own server)

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Documentation page (HTML) |
| `GET /api/ipl/live-scores` | Live scores for ongoing IPL 2026 matches |
| `GET /api/ipl/schedule` | Full IPL 2026 match schedule |
| `GET /api/ipl/points-table` | Current IPL 2026 points table |
| `GET /api/ipl/squad/{team_code}` | Team squad — codes: `mi` `csk` `rcb` `dc` `kkr` `pk` `rr` `srh` `gt` `lsg` |
| `GET /api/ipl/winners` | Historical IPL winners (2008–2025) |
| `GET /api/ipl/teams` | All team codes and names |
| `GET /healthz` | Health check |

## Sample Responses

### `GET /api/ipl/schedule`

```json
{
  "status": "success",
  "cached": false,
  "cache_ttl_seconds": 10,
  "data": {
    "series": "Indian Premier League 2026",
    "matches": [
      {
        "match_id": "149618",
        "date": "Sat, 28 Mar 2026",
        "match_desc": "1st Match",
        "status": "Match starts at Mar 28, 14:00 GMT",
        "state": "Upcoming",
        "team1": { "name": "Royal Challengers Bengaluru", "short_name": "RCB", "score": null },
        "team2": { "name": "Sunrisers Hyderabad", "short_name": "SRH", "score": null },
        "venue": "M.Chinnaswamy Stadium, Bengaluru",
        "start_date": "2026-03-28 07:30:00 PM IST"
      }
    ],
    "total": 74
  }
}
```

### `GET /api/ipl/points-table`

```json
{
  "status": "success",
  "cached": false,
  "cache_ttl_seconds": 10,
  "data": {
    "series": "Indian Premier League 2026",
    "teams": [
      {
        "team": "Mumbai Indians",
        "short_name": "MI",
        "played": 0,
        "won": 0,
        "lost": 0,
        "tied": 0,
        "no_result": 0,
        "nrr": "0.000",
        "points": 0
      }
    ],
    "total": 10
  }
}
```

### `GET /api/ipl/squad/mi`

```json
{
  "status": "success",
  "cached": false,
  "cache_ttl_seconds": 10,
  "data": {
    "team": "Mumbai Indians",
    "team_code": "mi",
    "players": [
      { "name": "Rohit Sharma" },
      { "name": "Suryakumar Yadav" },
      { "name": "Hardik Pandya" },
      { "name": "Jasprit Bumrah" }
    ],
    "total": 25
  }
}
```

### `GET /api/ipl/winners`

```json
{
  "status": "success",
  "cached": false,
  "cache_ttl_seconds": 10,
  "data": {
    "winners": [
      { "year": 2008, "winner": "Rajasthan Royals", "runner_up": "Chennai Super Kings" },
      { "year": 2009, "winner": "Deccan Chargers", "runner_up": "Royal Challengers Bangalore" },
      { "year": 2025, "winner": "Royal Challengers Bengaluru", "runner_up": "Punjab Kings" }
    ],
    "total": 18
  }
}
```

### `GET /api/ipl/teams`

```json
{
  "status": "success",
  "count": 10,
  "teams": {
    "csk": "Chennai Super Kings",
    "dc": "Delhi Capitals",
    "gt": "Gujarat Titans",
    "rcb": "Royal Challengers Bengaluru",
    "pk": "Punjab Kings",
    "kkr": "Kolkata Knight Riders",
    "srh": "Sunrisers Hyderabad",
    "rr": "Rajasthan Royals",
    "lsg": "Lucknow Super Giants",
    "mi": "Mumbai Indians"
  }
}
```

### `GET /api/ipl/live-scores`

```json
{
  "status": "success",
  "cached": false,
  "cache_ttl_seconds": 10,
  "data": {
    "series": "Indian Premier League 2026",
    "matches": [],
    "total": 0
  }
}
```

## Quick Start

### Local Development

```bash
pip install poetry
poetry install
poetry run fastapi dev app/index.py
```

Visit `http://localhost:8000` for the documentation page.

### Docker

```bash
docker build -t ipl-api .
docker run -p 8000:8000 ipl-api
```

## Data Sources

Data is scraped live from [Cricbuzz](https://www.cricbuzz.com) with automatic retry and 10-second TTL caching.

## Disclaimer

This is an unofficial API for educational purposes. Not affiliated with any cricket board.

## License

MIT
