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
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Choose the **Free** plan and click **Deploy**

### Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template?referralCode=surya)

Or manually:

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click **"New Project"** → **"Deploy from GitHub repo"**
3. Select this repo — Railway auto-detects the `Procfile`
4. Your API is live instantly

### Koyeb

1. Go to [koyeb.com](https://www.koyeb.com) and sign in
2. Click **"Create App"** → **"GitHub"**
3. Select this repo and set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Deploy — free tier available

### Docker (Self-Hosted)

```bash
docker build -t cricket-api .
docker run -p 8000:8000 cricket-api
```

## Quick Start (Local Development)

```bash
# Install dependencies
pip install poetry
poetry install

# Start the dev server
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000` for the documentation page.

## Data Sources

- [Cricbuzz](https://www.cricbuzz.com/) — Live cricket scores (scraped)
- [IPL 2025 API](https://github.com/cu-sanjay/IPL-2025-API-Free) — IPL-specific data

## Disclaimer

This is an unofficial API for educational purposes. Not affiliated with Cricbuzz or any cricket board.

## License

MIT
