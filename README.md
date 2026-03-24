# IPL 2026 Fantasy API

Free, unlimited, self-hosted JSON API for IPL 2026 data **with Fantasy Points system** and 10-second auto-refresh cache.

## Features

- **Live Scores** — Real-time IPL 2026 match scores, auto-updated every 10 seconds
- **Full Schedule** — Complete match schedule with dates, venues, and teams
- **Points Table** — Current standings with NRR, wins, losses
- **Team Squads** — All 10 IPL team squads for 2026 season
- **Historical Winners** — Every IPL winner from 2008 to 2025
- **Fantasy Players** — 241 players across 10 teams with role, price, overseas status, and images
- **Fantasy Points** — Auto-calculated per match from live Cricbuzz scorecard data
- **Admin Panel** — Add/remove players in real-time via web UI or API
- **Scoring Rules API** — Full fantasy scoring rules accessible via endpoint
- **No API Key** — Free, unlimited, zero config (admin endpoints require token)
- **Self-Hosted** — Deploy anywhere (Docker, Render, Vercel, your own server)

## API Endpoints

### IPL Data

| Endpoint | Description |
|---|---|
| `GET /` | Documentation page (HTML) |
| `GET /api/ipl/live-scores` | Live scores for ongoing IPL 2026 matches |
| `GET /api/ipl/schedule` | Full IPL 2026 match schedule |
| `GET /api/ipl/points-table` | Current IPL 2026 points table |
| `GET /api/ipl/squad/{team_code}` | Team squad — codes: `mi` `csk` `rcb` `dc` `kkr` `pk` `rr` `srh` `gt` `lsg` |
| `GET /api/ipl/winners` | Historical IPL winners (2008-2025) |
| `GET /api/ipl/teams` | All team codes and names |

### Fantasy Players

| Endpoint | Description |
|---|---|
| `GET /api/fantasy/players` | All fantasy players (supports `?team=csk` and `?role=Batsman` filters) |
| `GET /api/fantasy/players/{team_code}` | All players for a specific team with full details |
| `GET /api/fantasy/players/{team_code}/{role}` | Players filtered by team and role (`batsman`, `bowler`, `all_rounder`, `wicket_keeper`) |

### Fantasy Points

| Endpoint | Description |
|---|---|
| `GET /api/fantasy/points/{match_id}` | Auto-calculated fantasy points for all players in a match (from Cricbuzz scorecard) |
| `GET /api/fantasy/points/{match_id}/{team_code}` | Fantasy points for a specific team's players in a match |
| `GET /api/fantasy/leaderboard?match_id={id}` | Fantasy points leaderboard for a match (sorted by total points) |
| `GET /api/fantasy/scoring-rules` | Complete fantasy scoring rules |

### Player Match-Wise Points

| Endpoint | Description |
|---|---|
| `GET /api/fantasy/player/{player_name}/matches` | All match-wise fantasy points for a player (each match starts from 0, old data preserved) |
| `GET /api/fantasy/player/{player_name}/match/{match_id}` | A player's fantasy points for a specific match |
| `GET /api/fantasy/player/{player_name}/total` | Cumulative total points across all matches with per-match breakdown |
| `GET /api/fantasy/team/{team_code}/match-history` | Match-wise points for all players in a team, grouped by player |

### Admin (requires `Authorization: Bearer <token>`)

| Endpoint | Description |
|---|---|
| `GET /admin` | Admin panel web UI |
| `POST /api/admin/players/add` | Add a player to a team |
| `POST /api/admin/players/remove` | Remove a player from a team |
| `POST /api/admin/cache/clear` | Clear caches (optional `?match_id=`) |
| `GET /api/admin/token` | Verify admin token |

### Utility

| Endpoint | Description |
|---|---|
| `GET /healthz` | Health check |

## Fantasy Scoring Rules

### Batting Points
| Action | Points |
|---|---|
| Run scored | +1 |
| Boundary (4) | +4 bonus (total +5 per four) |
| Six | +7 bonus (total +8 per six) |
| 25 runs milestone | +4 bonus |
| 50 runs milestone | +8 bonus |
| 75 runs milestone | +12 bonus |
| 100 runs milestone | +16 bonus |
| Duck (0, dismissed) | -2 (batters/WK/all-rounders) |

**Example:** 50 runs with 5 fours = 50 (runs) + 20 (5×4 boundary bonus) + 8 (50-run milestone) = 78 points

### Strike Rate (min 10 balls faced)
| Strike Rate | Points |
|---|---|
| > 170 | +6 |
| 150-170 | +4 |
| 130-150 | +2 |
| 60-70 | -2 |
| 50-60 | -4 |
| < 50 | -6 |

### Bowling Points
| Action | Points |
|---|---|
| Wicket | +25 |
| LBW/Bowled bonus | +8 (total +33 per LBW/Bowled wicket) |
| 3 wickets | +4 bonus |
| 4 wickets | +8 bonus |
| 5 wickets | +16 bonus |
| Maiden over | +12 |

### Economy Rate (min 2 overs bowled)
| Economy | Points |
|---|---|
| < 5 | +6 |
| 5-6 | +4 |
| 6-7 | +2 |
| 9-10 | -2 |
| 10-11 | -4 |
| > 11 | -6 |

### Fielding Points
| Action | Points |
|---|---|
| Catch | +8 |
| 3 catches | +28 (24 catch points + 4 bonus) |
| Stumping | +12 |
| Run out (direct) | +12 |
| Run out (assist) | +6 |

### Extra
| Action | Points |
|---|---|
| Playing XI | +4 |
| Duck | -2 |

## Sample Responses

### `GET /api/fantasy/players/mi`

```json
{
  "status": "success",
  "team": "mi",
  "team_name": "Mumbai Indians",
  "players": [
    {
      "name": "Rohit Sharma",
      "role": "Batsman",
      "team": "mi",
      "base_price_cr": 16.3,
      "sold_price_cr": 16.3,
      "overseas": false,
      "retained": true,
      "image_url": "https://img1.hscicdn.com/..."
    }
  ],
  "total": 25
}
```

### `GET /api/fantasy/points/{match_id}`

```json
{
  "status": "success",
  "data": {
    "match_id": "149618",
    "players": [
      {
        "name": "Virat Kohli",
        "team": "rcb",
        "role": "Batsman",
        "fantasy_points": {
          "total_points": 85,
          "batting_points": 75,
          "bowling_points": 0,
          "fielding_points": 10,
          "batting_breakdown": {
            "runs": 52,
            "fours_bonus": 6,
            "sixes_bonus": 4,
            "half_century_bonus": 8,
            "strike_rate_bonus": 4
          }
        },
        "batting_stats": {
          "runs": 52,
          "balls": 35,
          "fours": 6,
          "sixes": 2,
          "strike_rate": 148.57,
          "is_out": true
        }
      }
    ],
    "total_players": 22
  }
}
```

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

## Quick Start

### Local Development

```bash
pip install poetry
poetry install
poetry run fastapi dev app/index.py
```

Visit `http://localhost:8000` for the documentation page. Visit `http://localhost:8000/admin` for the admin panel.

**Admin Token:** Set via `ADMIN_TOKEN` environment variable, or check server logs for the auto-generated token.

### Docker

```bash
docker build -t ipl-api .
docker run -p 8000:8000 -e ADMIN_TOKEN=your-secret-token ipl-api
```

## Data Sources

- **Match data** scraped live from [Cricbuzz](https://www.cricbuzz.com) with automatic retry and 10-second TTL caching.
- **Player data** loaded from embedded JSON (sourced from official IPL 2026 auction data).
- **Fantasy points** auto-calculated from Cricbuzz scorecard data per match.

## Disclaimer

This is an unofficial API for educational purposes. Not affiliated with any cricket board.

## License

MIT
