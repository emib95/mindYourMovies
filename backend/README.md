# MindYourMovies backend

FastAPI backend that gathers region-specific movie candidates from TMDb and asks
an LLM to choose a single recommendation.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

The server starts on `http://localhost:8000`.

## Environment

Secrets go in `.env` (see `.env.example`):

- `TMDB_API_KEY`: TMDb key for `/discover/movie`.
- `OPENAI_API_KEY`: optional for local development; without it, a deterministic
  demo recommendation is returned.

All other settings are defaults in `app/config.py` (region, vote thresholds,
candidate limit, geolocation URL, OpenAI model, and CORS origins). Change those
in git rather than in Railway or `.env`.

## Endpoint

`GET /api/location` resolves the user's country from hosting provider headers or
their public IP address, then falls back to `TMDB_REGION`.

`POST /api/recommendations` accepts provider access, desired mood, optional
group context, optional notes, `language`, `region`, and `allow_extra_costs` for
paid rentals or purchases. The backend uses title/reference searches, similar
movies, classic-aware discovery, and provider availability to build a ranked
candidate list before asking the LLM to choose one movie. The OpenAI request uses
web search so the response can include an official streaming-provider title page
or provider search URL instead of a TMDb watch page.
