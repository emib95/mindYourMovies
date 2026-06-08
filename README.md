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

## API

`POST /api/recommendations`

```json
{
  "providers": ["netflix", "disney"],
  "mood": "Something funny and easy to watch",
  "group_context": "Four friends after dinner",
  "notes": "No horror tonight"
}
```

Response:

```json
{
  "movie_title": "Example Movie",
  "provider": "Netflix",
  "watch_link": "https://www.themoviedb.org/movie/123/watch?locale=GB",
  "reason": "This best fits the requested mood.",
  "tmdb_id": 123
}
```
