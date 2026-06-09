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

- `TMDB_API_KEY`: TMDb key for `/discover/movie`.
- `TMDB_REGION`: fallback TMDb watch region, defaults to `GB`.
- `GEOLOCATION_API_URL`: optional IP geolocation endpoint template. Defaults to
  `https://ipwho.is/{ip}?fields=success,country_code`.
- `OPENAI_API_KEY`: optional for local development; without it, a deterministic
  demo recommendation is returned.
- `OPENAI_MODEL`: defaults to `gpt-4.1-mini`.
- `ALLOWED_ORIGINS`: JSON list of frontend origins.

## Endpoint

`GET /api/location` resolves the user's country from hosting provider headers or
their public IP address, then falls back to `TMDB_REGION`.

`POST /api/recommendations` accepts provider access, desired mood, optional
group context, optional notes, `language`, `region`, and `allow_extra_costs` for
paid rentals or purchases. It returns one movie title and one watch link.
