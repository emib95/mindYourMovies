# MindYourMovies backend

FastAPI backend that recommends one movie to watch now. The default path is an
**API-only agent**: an LLM drives a small toolbox over the TMDb API, evaluates
the results itself, and only finalises a movie once it is a strong, available
match — then asks Watchmode for a regional streaming deep link. If the agent is
disabled or fails, the backend falls back to the previous web-search LLM-first
flow and finally to the TMDb-first candidate flow.

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

- `TMDB_API_KEY`: TMDb key for search, discovery, details, and watch providers.
- `OPENAI_API_KEY`: optional for local development; without it the agent and
  LLM paths are skipped and a deterministic demo recommendation is returned.
- `WATCHMODE_API_KEY`: optional; enables regional streaming deep links on the
  agentic path. Without it the agent falls back to a provider search link.

All other settings are defaults in `app/config.py` (region, vote thresholds,
candidate limit, geolocation URL, OpenAI model, LLM-first timeout and batch
limits, agent toggle/model/timeout/iteration and strictness floors, and CORS
origins). Change those in git rather than in Railway or `.env`.

## Agentic recommendation path

`MovieRecommendationAgent` (`app/services/agent.py`) runs a tool-calling loop
against OpenAI with these TMDb-backed tools and no web search:

- `search_movies` — title/keyword search.
- `discover_movies` — genre, rating, vote-count, era, language, and runtime
  filters, pre-filtered to titles available on the user's providers/region.
- `movie_details` — overview, tagline, runtime, genres, cast, director, keywords.
- `check_availability` — confirms availability on the selected providers.
- `finalize_recommendation` — locks in one movie; re-verifies availability and
  rejects excluded or unavailable titles so the agent keeps searching.

The full tool-call transcript is replayed to the model each turn, so it
remembers every movie and response it has seen. On finalisation the verified
TMDb id is resolved to a Watchmode deep link for the user's region and providers.

Everything is logged through `RecommendationTracer`: each LLM turn (with token
usage), each TMDb/Watchmode API call (params, response summary, latency), and an
end-to-end summary with total latency, LLM/tool call counts, and total tokens.

## Endpoint

`GET /api/location` resolves the user's country from hosting provider headers or
their public IP address, then falls back to `TMDB_REGION`.

`POST /api/recommendations` accepts provider access, desired mood, optional
group context, optional notes, `language`, `region`, and `allow_extra_costs` for
paid rentals or purchases. The backend first asks OpenAI with web search for one
matching movie available in the user's country, then checks that title in TMDb
for the requested country, provider, and monetization type. If it does not
verify, it requests another single-title attempt up to the configured batch
limit. If this OpenAI-first path fails or exceeds the timeout, the endpoint
falls back to the original flow: title/reference searches, similar movies,
classic-aware discovery, and provider availability build a ranked TMDb candidate
list before asking the LLM to choose one movie. OpenAI web search is also used to
find an official streaming-provider title page when one is not already known.
After a movie has already been selected and verified, a separate best-effort
OpenAI enrichment may add optional `movie_details` with a spoiler-free intro,
notable actors, IMDb rating, and Rotten Tomatoes score. Missing details do not
change the recommendation path.

## LLM prompt construction

The recommendation engine builds prompts in `app/services/llm.py`:

1. `availability_region` is derived from the request `region`, or from the
   `TMDB_REGION` default if the request did not include one.
2. The system prompt explains the task, output schema, provider-link rules, and
   the instruction that `availability_region` is only a streaming-market
   constraint. The model is explicitly told not to treat it as a preference for
   movies from, set in, or about that country.
3. The user payload is JSON. Availability, providers, extra-cost preference, and
   response language are top-level fields. Actual taste signals are isolated in
   `user_preferences`, which contains only `mood`, `group_context`, and `notes`.
4. The LLM-first path asks OpenAI for one title, then verifies that title against
   TMDb availability for the selected providers and monetization types.
5. The TMDb-first fallback sends a pre-filtered candidate list to OpenAI and asks
   it to choose exactly one title. Those candidates are already filtered by
   `availability_region`, so the prompt tells the model to use the region for
   availability and watch-link lookup, not as a country-of-origin signal.
