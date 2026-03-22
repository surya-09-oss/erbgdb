# Cricket API

Free, unlimited, self-hosted JSON API for live cricket scores, IPL 2025 data, and more.
Fully compatible with [sanwebinfo/cricket-api](https://github.com/sanwebinfo/cricket-api) format.

## Features

- **Live Cricket Scores** — All formats (T20, ODI, Test) scraped from Cricbuzz
- **Cricket-API Compatible** — Drop-in replacement for [sanwebinfo/cricket-api](https://github.com/sanwebinfo/cricket-api) (`/score` and `/score/live` endpoints)
- **IPL 2025 Data** — Live scores, schedule, points table, team squads, historical winners
- **Auto-Updating Background Task** — Data refreshes automatically every 10 seconds in the background
- **10-Second TTL Cache** — Always fresh data with zero delay
- **No API Key Required** — Completely free and unlimited
- **Self-Hosted** — Deploy anywhere (Docker, Render, Vercel, your own server)
- **Clean Documentation** — Black & white docs page at the root URL

## API Endpoints

### Cricket-API Compatible (from [sanwebinfo/cricket-api](https://github.com/sanwebinfo/cricket-api))

| Endpoint | Description |
|---|---|
| `GET /score?id={id}` | Match score — flat JSON format (cricket-api compatible) |
| `GET /score/live?id={id}` | Match score — nested JSON format (cricket-api compatible) |

### General Cricket

| Endpoint | Description |
|---|---|
| `GET /` | Documentation page (HTML) |
| `GET /api/live-matches` | All current live cricket matches |
| `GET /api/match-score?id={id}` | Detailed live score for a specific match |
| `GET /healthz` | Health check |

### IPL 2025

| Endpoint | Description |
|---|---|
| `GET /api/ipl/live-scores` | IPL 2025 live scores |
| `GET /api/ipl/schedule` | IPL 2025 match schedule |
| `GET /api/ipl/points-table` | IPL 2025 points table |
| `GET /api/ipl/squad/{team_code}` | Team squad (mi, csk, rcb, dc, kkr, pk, rr, srh, gt, lsg) |
| `GET /api/ipl/winners` | Historical IPL winners |
| `GET /api/ipl/teams` | All team codes |

## Auto-Updating

The API runs a **background task** that automatically fetches and caches live match data from Cricbuzz every **10 seconds**. You never need to trigger a refresh — data is always up to date.

All endpoints also use a 10-second TTL cache, so individual requests are served instantly from cache and automatically refreshed.

## Cricket-API Compatible Endpoints

These endpoints return data in the exact same JSON format as [sanwebinfo/cricket-api](https://github.com/sanwebinfo/cricket-api), so you can use this as a drop-in replacement.

### `GET /score?id={match_id}` — Flat JSON

```json
{
  "title": "Australia vs Pakistan, 2nd Test - Live Cricket Score",
  "update": "Day 1: 3rd Session",
  "livescore": "AUS 168/3 (60)",
  "runrate": "CRR: 2.8",
  "batterone": "Travis Head",
  "batsmanonerun": "5",
  "batsmanoneball": "(5)",
  "batsmanonesr": "100",
  "battertwo": "Marnus Labuschagne",
  "batsmantworun": "36",
  "batsmantwoball": "(98)",
  "batsmantwosr": "36.73",
  "bowlerone": "Shaheen Afridi",
  "bowleroneover": "19",
  "bowleronerun": "61",
  "bowleronewickers": "0",
  "bowleroneeconomy": "3.21",
  "bowlertwo": "Aamer Jamal",
  "bowlertwoover": "12",
  "bowlertworun": "37",
  "bowlertwowickers": "1",
  "bowlertwoeconomy": "3.08"
}
```

### `GET /score/live?id={match_id}` — Nested JSON

```json
{
  "success": "true",
  "livescore": {
    "title": "Australia vs Pakistan, 2nd Test",
    "update": "Day 1: 3rd Session",
    "current": "AUS 168/3 (60)",
    "runrate": "CRR: 2.8",
    "batsman": "Travis Head",
    "batsmanrun": "5",
    "ballsfaced": "(5)",
    "sr": "100",
    "batsmantwo": "Marnus Labuschagne",
    "batsmantworun": "36",
    "batsmantwoballfaced": "(98)",
    "batsmantwosr": "36.73",
    "bowler": "Shaheen Afridi",
    "bowlerover": "19",
    "bowlerruns": "61",
    "bowlerwickets": "0",
    "bowlereconomy": "3.21",
    "bowlertwo": "Aamer Jamal",
    "bowlertwoover": "12",
    "bowlertworuns": "37",
    "bowlertwowickets": "1",
    "bowlertwoeconomy": "3.08"
  }
}
```

## Deploy for Free (One-Click)

### Vercel (Recommended)

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fsurya-09-oss%2Ferbgdb)

Or manually:

1. Fork this repo
2. Go to [vercel.com](https://vercel.com) and sign in with GitHub
3. Click **"New Project"** and import this repo
4. Vercel auto-detects the config — just click **Deploy**
5. Your API is live at `https://your-project.vercel.app`

### Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/surya-09-oss/erbgdb)

Or manually:

1. Go to [render.com](https://render.com) and sign in
2. Click **"New Web Service"** and connect this repo
3. Set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.index:app --host 0.0.0.0 --port $PORT`
4. Choose the **Free** plan and click **Deploy**

### Railway

Or:

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select this repo — Railway auto-detects the `Procfile`
4. Your API is live instantly

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/github?repo=surya-09-oss/erbgdb)

### Koyeb

1. Go to [koyeb.com](https://www.koyeb.com) and sign in
2. Click **"Create App"** → **"GitHub"**
3. Select this repo and set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.index:app --host 0.0.0.0 --port $PORT`
4. Deploy — free tier available

### Docker (Self-Hosted)

```bash
docker build -t cricket-api .
docker run -p 8000:8000 cricket-api
```

## Quick Start (Local Development)

```bash
# Install dependencies
pip install -r requirements.txt

# Start the dev server
uvicorn app.index:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000` for the documentation page.

## Data Sources

- [Cricbuzz](https://www.cricbuzz.com/) — Live cricket scores (scraped)
- [sanwebinfo/cricket-api](https://github.com/sanwebinfo/cricket-api) — Cricket-API compatible JSON format
- [IPL 2025 API](https://github.com/cu-sanjay/IPL-2025-API-Free) — IPL-specific data

## Disclaimer

This is an unofficial API for educational purposes. Not affiliated with Cricbuzz or any cricket board.

## License

MIT
