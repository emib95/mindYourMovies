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

## OpenAI response scenarios

The backend includes 30 deterministic OpenAI request scenarios in
`tests/evals/openai_scenarios.py`. Each scenario builds the same payload shape
the app sends to OpenAI: region, user answers, and candidate movies.

Run the validation tests without making OpenAI calls:

```bash
python -m unittest discover -s tests
```

Analyze deterministic fallback responses:

```bash
python -m tests.evals.analyze_openai_responses
```

Analyze live OpenAI responses when `OPENAI_API_KEY` is configured:

```bash
python -m tests.evals.analyze_openai_responses --live --output reports/openai-eval.json
```

The report summarizes required fields, whether the returned title and watch link
match the candidate list, provider consistency, fallback usage, and per-scenario
response details.
