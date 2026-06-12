# MindYourMovies

MindYourMovies is a full-stack skeleton for reducing movie-night indecision. The
React TypeScript frontend asks a few focused questions, and the FastAPI backend
uses an LLM plus TMDb availability checks to return exactly one movie
recommendation with a watch link.

## Stack

- Frontend: React, TypeScript, Vite
- Backend: Python, FastAPI, httpx
- Data source: TMDb watch-provider data for the UK (`TMDB_REGION=GB`)
- AI selection: OpenAI Responses API with web search via the `openai` Python SDK

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

Copy `backend/.env.example` to `backend/.env` and set the two API keys:

- `TMDB_API_KEY`: TMDb API key used to fetch UK movie availability.
- `OPENAI_API_KEY`: LLM API key used to choose the final movie.

All other backend settings (region, vote thresholds, OpenAI model, LLM-first
timeout and batch limits, CORS origins, and so on) live in
`backend/app/config.py` and are tracked in git.

If keys are not configured, the backend returns a deterministic recommendation
from demo candidates so the frontend can still be exercised.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend defaults live in `frontend/src/config.ts`. Local dev talks to
`http://localhost:8000`; production builds use `https://api.mindyourmovies.com`
automatically. Optional `VITE_*` overrides are documented in
`frontend/.env.example`.

The small "Buy me a coffee" support section uses Emilio's Stripe Payment Link
and `/emilio-banqueri.jpg` by default. Place the photo in
`frontend/public/emilio-banqueri.jpg`.

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
3. **Variables** (secrets only — everything else is in `backend/app/config.py`):

```env
TMDB_API_KEY=<your key>
OPENAI_API_KEY=<your key>
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

3. **Environment variables:** none required. Defaults are in
   `frontend/src/config.ts` and production builds pick
   `https://api.mindyourmovies.com` automatically.

4. **Custom domains:** `mindyourmovies.com` and `www.mindyourmovies.com`

### Stripe donations

The app uses a Stripe Payment Link for donations, so no Stripe secret key is
stored in the frontend or backend.

1. Create or sign in to a Stripe account at [dashboard.stripe.com](https://dashboard.stripe.com).
2. In Stripe, go to **Payment Links** and create a new link.
3. Add a donation-style product such as "Buy me a coffee". For flexible support,
   enable customer-adjustable quantity or create a few fixed donation prices.
4. Copy the published payment link URL. The current donation link is
   `https://buy.stripe.com/28E5kD9Am5ku4DIavWfYY00`.
5. Save the creator photo as `frontend/public/emilio-banqueri.jpg`, or override
   `VITE_CREATOR_PHOTO_URL` in `frontend/.env` if needed.
6. Donation and photo URLs are configured in `frontend/src/config.ts`. Override
   with `VITE_*` variables only when you need a non-default value.

### Troubleshooting

| Issue                         | Fix                                                        |
| ----------------------------- | ---------------------------------------------------------- |
| Blank white frontend page     | Publish the built output (`frontend/dist`), not raw `frontend` |
| `_redirects` infinite loop    | Use Wrangler's SPA fallback; do not deploy a catch-all `_redirects` rule |
| CORS error in browser         | Add the frontend URL to `allowed_origins` in `config.py`   |
| Frontend calls `localhost`    | Redeploy from `main` — production URL is in `src/config.ts` |
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

The backend first asks OpenAI with web search for one movie that matches the
prompt and should be available in the selected country/providers, then verifies
that title against TMDb watch availability before returning it. If the suggested
title does not verify, the backend requests another single-title attempt up to
the configured batch limit. If the OpenAI-first path fails or exceeds the timeout, the backend
falls back to the original TMDb-first workflow: it searches for explicit
title/reference requests, expands from TMDb similar/recommended movies, uses
classic-aware discovery when the prompt asks for cinema classics or masterpieces,
and sends up to 60 ranked candidates to the LLM. OpenAI web search is also used
to find an official provider deep link, or an official provider search page when
a title page is not available.

Response:

```json
{
  "movie_title": "Example Movie",
  "provider": "Netflix",
  "watch_link": "https://www.netflix.com/title/123456",
  "reason": "This best fits the requested mood.",
  "why_recommended": "It matches the light tone you asked for and is available from one of your selected providers without an extra rental fee.",
  "tmdb_id": 123
}
```

## Research notes

- [Direct streaming provider links](docs/provider-links-research.md): options
  for replacing TMDb watch-page links with Netflix/Disney+/other provider links.
