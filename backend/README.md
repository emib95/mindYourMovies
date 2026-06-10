# MindYourMovies backend

FastAPI backend that asks an LLM for region-specific movie ideas, verifies them
against TMDb watch availability, and falls back to the original TMDb-first
candidate flow when needed.

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

- `TMDB_API_KEY`: TMDb key for `/discover/movie`.
- `TMDB_REGION`: fallback TMDb watch region, defaults to `GB`.
- `TMDB_MIN_VOTE_AVERAGE`: minimum TMDb user rating for candidates, defaults to
  `7.0`.
- `TMDB_MIN_VOTE_COUNT`: minimum number of TMDb votes for candidates, defaults
  to `500`. This is used as the audience-size signal because TMDb does not expose
  raw per-movie view counts.
- `TMDB_CANDIDATE_LIMIT`: maximum number of ranked candidates sent to the LLM,
  defaulting to `60`.
- `GEOLOCATION_API_URL`: optional IP geolocation endpoint template. Defaults to
  `https://ipwho.is/{ip}?fields=success,country_code`.
- `OPENAI_API_KEY`: optional for local development; without it, a deterministic
  demo recommendation is returned.
- `OPENAI_MODEL`: defaults to `gpt-4.1-mini`.
- `LLM_FIRST_TIMEOUT_SECONDS`: maximum time for the OpenAI-first path before
  falling back to the TMDb-first workflow, defaulting to `60`.
- `LLM_FIRST_MAX_BATCHES`: maximum five-title OpenAI batches to verify before
  falling back, defaulting to `3`.
- `ALLOWED_ORIGINS`: JSON list of frontend origins.

## Endpoint

`GET /api/location` resolves the user's country from hosting provider headers or
their public IP address, then falls back to `TMDB_REGION`.

`POST /api/recommendations` accepts provider access, desired mood, optional
group context, optional notes, `language`, `region`, and `allow_extra_costs` for
paid rentals or purchases. The backend first asks OpenAI with web search for five
matching movies available in the user's country, then checks each title in TMDb
for the requested country, provider, and monetization type. If none of those
titles verify, it requests another five-title batch up to the configured batch
limit. If this OpenAI-first path fails or exceeds the timeout, the endpoint
falls back to the original flow: title/reference searches, similar movies,
classic-aware discovery, and provider availability build a ranked TMDb candidate
list before asking the LLM to choose one movie. OpenAI web search is also used to
find an official streaming-provider title page when one is not already known.
