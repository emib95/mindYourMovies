# Direct streaming provider links research

## Context in this repository

The backend currently uses TMDb `/discover/movie` to find UK candidates for the
selected providers. It then builds a TMDb watch URL itself:

```py
watch_link=f"https://www.themoviedb.org/movie/{movie['id']}/watch?locale={self.settings.tmdb_region}"
```

That explains why recommendations send users to TMDb rather than directly to
Netflix, Disney+, YouTube, NOW, or another provider.

## Does TMDb provide direct provider links?

No. TMDb does provide a watch-provider endpoint:

```text
GET /3/movie/{movie_id}/watch/providers
```

It returns country-specific provider availability, with sections such as
`flatrate`, `rent`, `buy`, `ads`, and `free`, plus a `link` field. However, the
official TMDb documentation says the endpoint is "not going to return full deep
links" and is "just enough information to display what's available where." The
`link` field is still a TMDb watch page URL, intended to provide the actual
provider links from TMDb's UI.

Important compliance notes:

- TMDb watch-provider data is powered by JustWatch and requires JustWatch
  attribution.
- TMDb requires TMDb attribution and logo usage for API data.
- TMDb API terms limit caching to no longer than 6 months and require a
  commercial agreement for commercial use.

## Should we scrape provider links from TMDb?

Not recommended.

Reasons:

- **Policy/compliance risk:** TMDb exposes an official API but explicitly does
  not expose full deep links there. Scraping around that boundary is risky,
  especially because provider availability comes from JustWatch and has its own
  attribution/partner terms.
- **Brittleness:** TMDb watch pages are rendered for users, not as a stable data
  contract. DOM structure, tracking redirects, region behavior, and provider
  link behavior can change without notice.
- **Operational cost:** Scraping every candidate at request time would add more
  network hops, HTML parsing, redirect handling, and anti-bot failure modes to
  the recommendation path.
- **Quality:** The result would still need provider normalization, region
  filtering, stale-link handling, and validation.

## Would fetching direct links at request time increase latency?

It depends on the source:

- **TMDb watch-provider endpoint:** For the current flow, adding one
  `/movie/{id}/watch/providers` request per candidate would mean up to 12 extra
  API calls. If done sequentially, that would noticeably slow responses. If done
  concurrently with `httpx.AsyncClient`, it is more manageable but still adds
  dependency latency, rate-limit pressure, and another failure path. It still
  would not solve direct provider links.
- **Scraping TMDb pages:** This would likely add much more latency and variance
  than API calls because HTML pages are heavier and less predictable.
- **Provider-link API:** One lookup for the final selected movie would add a
  single API call after the LLM choice. Looking up all 12 candidates before the
  LLM would improve link-aware selection but add more request cost. A cache can
  avoid repeated lookups for popular titles.

For this product, direct-link enrichment should happen either:

1. after the final movie is selected, with a fallback to the current TMDb URL, or
2. ahead of recommendation only for cached/precomputed popular titles.

## Is a scheduled daily scraper/database a good idea?

A daily database job is a good architecture, but it should use licensed APIs
rather than scraped TMDb pages.

Recommended shape:

- Keep TMDb as the discovery source or switch discovery to a provider-link API.
- Store provider-link records keyed by:
  - `tmdb_id`
  - `region`
  - `provider`
  - `monetization_type` (`subscription`, `rent`, `buy`, `free`, etc.)
  - `web_url`
  - optional app/video deeplinks if the provider supports them
  - `source`
  - `fetched_at`
  - `expires_at` or TTL
- Refresh popular/top-by-genre titles daily.
- On a cache miss, fetch on demand and write through to the cache.
- Keep the current TMDb watch URL as a safe fallback.

This gives predictable request latency and keeps API usage under control without
depending on brittle scraping.

## Alternative APIs with direct provider links

### Streaming Availability API by Movie of the Night

Best initial fit for this app.

- Supports movies and series across 66 countries.
- Can retrieve shows by IMDb ID or TMDb ID, which matches this app's existing
  TMDb-based flow.
- Returns `streamingOptions` by country.
- Each streaming option includes a direct service `link`; some services also
  include a `videoLink` to start playback where applicable.
- Supports searching/filtering by streaming service, genre, release year, and
  popularity, so it could eventually replace or augment TMDb discovery.
- Has a free developer plan and paid plans; verify quotas and commercial terms
  before production use.

Implementation sketch:

1. Add `STREAMING_AVAILABILITY_API_KEY`.
2. After the recommendation engine selects a movie, call
   `GET https://api.movieofthenight.com/v4/shows/movie/{tmdb_id}` with
   `country=gb`. The documented `/v4/shows/{id}` endpoint accepts TMDb IDs in
   the `movie/{id}` form; for example, Titanic is `movie/597`.
3. Select the first `streamingOptions.gb` entry matching the recommended
   provider and preferred monetization type. Map this app's `TMDB_REGION=GB`
   setting to the API's lower-case country code.
4. Return `videoLink` if present; otherwise return `link`; otherwise fall back to
   the TMDb watch page.

### Watchmode

Strong option if budget allows paid plans.

- Supports 200+ services and 50+ countries, including Great Britain.
- Returns title sources with `web_url`.
- Paid plans include iOS/Android deeplinks and episode-level links.
- Offers a TMDb/IMDb mapping CSV and search endpoints for mapping existing TMDb
  IDs to Watchmode title IDs.
- Free tier is limited to 2,500 monthly requests, non-commercial use, and up to
  three countries; paid plans listed at the time of research start at $349/month.

Implementation sketch:

1. Map TMDb IDs to Watchmode IDs via `/search/` or their title ID map.
2. Call `/v1/title/{watchmode_id}/sources/?regions=GB`.
3. Match the selected provider and return `web_url`, with paid deeplinks later
   if needed.

### JustWatch Partner API / Widget

Potentially the most direct source because TMDb watch-provider data is powered
by JustWatch.

- Official partner API can query by TMDb ID and returns VOD offers.
- Requires a partner contract/token.
- Requires branded JustWatch links/attribution.
- The widget may be easier if the desired UX can tolerate embedding a provider
  availability widget rather than controlling the exact outbound link.

### Utelly / Synamedia

Commercial content discovery option.

- Focused on TV/OTT search, metadata aggregation, and availability.
- Historically available through RapidAPI for developer experiments.
- Good to evaluate only if Streaming Availability API or Watchmode do not meet
  UK provider coverage/terms.

### Provider-specific APIs

Netflix, Disney+, NOW/HBO, and similar services generally do not expose simple
public catalog APIs with stable movie-level deep links for third-party consumer
apps. Provider-specific IDs and URLs are difficult to derive reliably from TMDb
IDs, so a specialist availability aggregator is the practical path.

## Recommendation

Do not scrape TMDb. Keep the current TMDb URL as fallback and integrate a
licensed provider-link API.

The most pragmatic next step is:

1. Start with Streaming Availability API because it accepts TMDb IDs and returns
   direct links in the shape this app needs.
2. Add a backend enrichment layer that runs after final movie selection to keep
   latency and API usage low.
3. Add a small cache keyed by TMDb ID, provider, and region. In production,
   Redis, Postgres, or the existing hosting platform's managed datastore would
   work; for local development an in-memory cache is enough.
4. Add a scheduled refresh job for popular/top-by-genre movies only after the
   on-demand integration proves useful.
5. Add required TMDb and JustWatch/provider attribution in the UI before shipping
   this publicly.

This approach improves the user experience with low implementation risk while
preserving a robust fallback when a provider-link API misses a title.
