# Cricket API

Free, unlimited, self-hosted JSON API for live cricket scores, IPL 2025 data, and more.

## Features

- **Live Cricket Scores** — All formats (T20, ODI, Test) scraped from Cricbuzz
- **IPL 2025 Data** — Live scores, schedule, points table, team squads, historical winners
- **10-Second Auto-Refresh Cache** — Always fresh data with zero delay
- **No API Key Required** — Completely free and unlimited
- **Self-Hosted** — Deploy anywhere (Docker, Render, Vercel, your own server)
- **Clean Documentation** — Black & white docs page at the root URL

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Documentation page (HTML) |
| `GET /api/live-matches` | All current live cricket matches |
| `GET /api/match-score?id={id}` | Detailed live score for a specific match |
| `GET /api/ipl/live-scores` | IPL 2025 live scores |
| `GET /api/ipl/schedule` | IPL 2025 match schedule |
| `GET /api/ipl/points-table` | IPL 2025 points table |
| `GET /api/ipl/squad/{team_code}` | Team squad (mi, csk, rcb, dc, kkr, pk, rr, srh, gt, lsg) |
| `GET /api/ipl/winners` | Historical IPL winners |
| `GET /api/ipl/teams` | All team codes |
| `GET /healthz` | Health check |

## Quick Start

### Local Development

```bash
# Install dependencies
pip install poetry
poetry install

# Start the dev server
poetry run fastapi dev app/main.py
```

Visit `http://localhost:8000` for the documentation page.

### Docker

```bash
docker build -t cricket-api .
docker run -p 8000:8000 cricket-api
```

## Data Sources

- [Cricbuzz](https://www.cricbuzz.com/) — Live cricket scores (scraped)
- [IPL 2025 API](https://github.com/cu-sanjay/IPL-2025-API-Free) — IPL-specific data

## Disclaimer

This is an unofficial API for educational purposes. Not affiliated with Cricbuzz or any cricket board.

## License

MIT
