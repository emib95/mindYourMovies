# MindYourMovies backend

FastAPI backend that gathers region-specific movie candidates from TMDb, asks an
LLM to choose a single recommendation, and can optionally resolve the final TMDb
watch link to an official provider page.

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
- `PROVIDER_LINK_SEARCH_ENABLED`: enables official provider link lookup when a
  Bing key is configured. Defaults to `true`.
- `BING_SEARCH_API_KEY`: optional Bing Web Search key. Link lookup runs only
  after the final recommendation is selected, and the TMDb watch link is kept if
  no confident official-provider result is found.
- `BING_SEARCH_ENDPOINT`: Bing Web Search endpoint. Defaults to
  `https://api.bing.microsoft.com/v7.0/search`.
- `OPENAI_API_KEY`: optional for local development; without it, a deterministic
  demo recommendation is returned.
- `OPENAI_MODEL`: defaults to `gpt-4.1-mini`.
- `ALLOWED_ORIGINS`: JSON list of frontend origins.

## Endpoint

`GET /api/location` resolves the user's country from hosting provider headers or
their public IP address, then falls back to `TMDB_REGION`.

`POST /api/recommendations` accepts provider access, desired mood, optional
group context, optional notes, `language`, `region`, and `allow_extra_costs` for
paid rentals or purchases. The backend uses title/reference searches, similar
movies, classic-aware discovery, and provider availability to build a ranked
candidate list before asking the LLM to choose one movie. If Bing Web Search is
configured, it then searches for an official page on the selected provider's
domain and replaces the TMDb watch link only for confident matches.
