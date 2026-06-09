# MindYourMovies

MindYourMovies is a full-stack skeleton for reducing movie-night indecision. The
React TypeScript frontend asks a few focused questions, and the FastAPI backend
uses UK TMDb availability plus an LLM to return exactly one movie recommendation
with a watch link.

## Stack

- Frontend: React, TypeScript, Vite
- Backend: Python, FastAPI, httpx
- Data source: TMDb watch-provider data for the UK (`TMDB_REGION=GB`)
- AI selection: OpenAI-compatible chat completion via the `openai` Python SDK

## Project structure

```text
backend/
  app/
    main.py              # FastAPI app and recommendation endpoint
    schemas.py           # API request/response models
    services/
      tmdb.py            # UK TMDb provider aggregation
      llm.py             # Single-movie LLM selection
  requirements.txt
frontend/
  src/
    App.tsx              # Provider/mood questionnaire
    App.css
```

## Local setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Set these values in `backend/.env`:

- `TMDB_API_KEY`: TMDb API key used to fetch UK movie availability.
- `TMDB_MIN_VOTE_AVERAGE`: minimum TMDb user rating for recommendation
  candidates, defaulting to `6.5`.
- `TMDB_MIN_VOTE_COUNT`: minimum TMDb vote count for recommendation candidates,
  defaulting to `50`. TMDb does not provide raw movie view counts, so vote count
  and popularity are used as audience-size signals.
- `OPENAI_API_KEY`: LLM API key used to choose the final movie.
- `OPENAI_MODEL`: Model name, defaulting to `gpt-4.1-mini`.

If keys are not configured, the backend returns a deterministic recommendation
from demo candidates so the frontend can still be exercised.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

The frontend expects the API at `VITE_API_BASE_URL`, defaulting to
`http://localhost:8000`.

## Deploy

Production uses **Cloudflare Pages** (frontend) and **Railway** (backend).
Pushes to `main` auto-deploy both via their GitHub integrations. GitHub Actions
(`.github/workflows/ci.yml`) verifies builds on pull requests.

| Service  | URL                              | Host      |
| -------- | -------------------------------- | --------- |
| Frontend | `https://mindyourmovies.com`     | Cloudflare Pages |
| Backend  | `https://api.mindyourmovies.com` | Railway   |

### Prerequisites

- Code merged on `main`
- Domain `mindyourmovies.com` on Cloudflare (DNS managed there)

### Backend (Railway)

1. [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. **Settings → Root Directory:** `backend`
3. **Variables:**

```env
ALLOWED_ORIGINS=["https://mindyourmovies.com","https://www.mindyourmovies.com"]
TMDB_API_KEY=<your key>
OPENAI_API_KEY=<your key>
TMDB_REGION=GB
OPENAI_MODEL=gpt-4.1-mini
```

4. **Settings → Networking → Custom Domain:** `api.mindyourmovies.com`
5. In Cloudflare DNS, add a **CNAME** for `api` pointing at Railway's target.
   Set proxy to **DNS only** (grey cloud).
6. Verify: `curl https://api.mindyourmovies.com/health` → `{"status":"ok"}`

`backend/railway.toml` sets the start command and health check.

### Frontend (Cloudflare Pages)

1. Cloudflare Dashboard → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**
2. Build settings:

| Setting              | Value           |
| -------------------- | --------------- |
| Production branch    | `main`          |
| Root directory       | `frontend`      |
| Build command        | `npm run build` |
| Build output         | `dist`          |

3. **Environment variables → Production:**

```env
VITE_API_BASE_URL=https://api.mindyourmovies.com
```

4. **Custom domains:** `mindyourmovies.com` and `www.mindyourmovies.com`

Rebuild after changing `VITE_API_BASE_URL` — Vite bakes it in at build time.

### Troubleshooting

| Issue                         | Fix                                                        |
| ----------------------------- | ---------------------------------------------------------- |
| Blank white frontend page     | Publish the built output (`frontend/dist`), not raw `frontend` |
| `_redirects` infinite loop    | Use Wrangler's SPA fallback; do not deploy a catch-all `_redirects` rule |
| CORS error in browser         | Add the frontend URL to `ALLOWED_ORIGINS` on Railway       |
| Frontend calls `localhost`    | Set `VITE_API_BASE_URL` in Cloudflare and redeploy         |
| `api` subdomain SSL fails     | Disable Cloudflare proxy (grey cloud) on the `api` CNAME   |

## API

`POST /api/recommendations`

```json
{
  "providers": ["netflix", "disney", "prime"],
  "mood": "Something funny and easy to watch",
  "allow_extra_costs": false,
  "group_context": "Four friends after dinner",
  "notes": "No horror tonight"
}
```

`allow_extra_costs` controls TMDb watch monetization filtering. When it is
`false`, recommendations exclude titles that are only available as paid rentals
or purchases. Set it to `true` to include rent/buy options such as many YouTube
movies.

The backend also filters TMDb candidates by rating and vote count before asking
the LLM to choose. The LLM receives each candidate's rating, vote count, and
popularity so it can favor movies with stronger audience signals.

Response:

```json
{
  "movie_title": "Example Movie",
  "provider": "Netflix",
  "watch_link": "https://www.themoviedb.org/movie/123/watch?locale=GB",
  "reason": "This best fits the requested mood.",
  "why_recommended": "It matches the light tone you asked for and is available from one of your selected providers without an extra rental fee.",
  "tmdb_id": 123
}
```
