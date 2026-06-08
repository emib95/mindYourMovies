# MindYourMovies backend

FastAPI backend that gathers UK movie candidates from TMDb and asks an LLM to
choose a single recommendation.

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
- `TMDB_REGION`: defaults to `GB`.
- `OPENAI_API_KEY`: optional for local development; without it, a deterministic
  demo recommendation is returned.
- `OPENAI_MODEL`: defaults to `gpt-4.1-mini`.
- `ALLOWED_ORIGINS`: JSON list of frontend origins.

## Endpoint

`POST /api/recommendations` accepts provider access, desired mood, optional
group context, and optional notes. It returns one movie title and one watch link.
