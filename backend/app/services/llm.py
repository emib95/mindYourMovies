import json

from openai import AsyncOpenAI, OpenAIError

from app.config import Settings
from app.schemas import MovieCandidate, RecommendationRequest, RecommendationResponse


LANGUAGE_LABELS = {
    "en": "English",
    "es": "Spanish",
}

FALLBACK_REASONS = {
    "en": "Picked from candidates available in {region} using your provider and mood answers.",
    "es": "Elegida entre opciones disponibles en {region} usando tus plataformas y preferencias.",
}


class RecommendationEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def recommend(
        self,
        recommendation_request: RecommendationRequest,
        candidates: list[MovieCandidate],
    ) -> RecommendationResponse:
        if not candidates:
            raise ValueError("At least one movie candidate is required.")

        if not self.settings.openai_api_key:
            return self._fallback_recommendation(recommendation_request, candidates)

        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        try:
            response = await client.chat.completions.create(
                model=self.settings.openai_model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You help people stop scrolling and pick one movie. "
                            "Choose exactly one title from the candidate list. "
                            "Favor well-rated candidates with stronger vote counts and popularity. "
                            "Respect the user's allow_extra_costs preference when explaining the choice. "
                            "Return JSON only with movie_title, provider, watch_link, and reason. "
                            f"Write the reason in {LANGUAGE_LABELS[recommendation_request.language]}. "
                            "Do not invent titles or links."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "region": self._region(recommendation_request),
                                "language": recommendation_request.language,
                                "user_answers": recommendation_request.model_dump(mode="json"),
                                "candidates": [
                                    candidate.model_dump(mode="json") for candidate in candidates
                                ],
                            }
                        ),
                    },
                ],
            )
        except OpenAIError:
            return self._fallback_recommendation(recommendation_request, candidates)

        content = response.choices[0].message.content or "{}"
        try:
            llm_payload = json.loads(content)
        except json.JSONDecodeError:
            return self._fallback_recommendation(recommendation_request, candidates)

        selected = self._candidate_by_title(
            candidates,
            str(llm_payload.get("movie_title", "")),
        )
        if selected is None:
            return self._fallback_recommendation(recommendation_request, candidates)

        return RecommendationResponse(
            movie_title=selected.title,
            provider=str(llm_payload.get("provider") or ", ".join(selected.provider_names)),
            watch_link=selected.watch_link,
            reason=str(
                llm_payload.get("reason")
                or "This best matches the mood and provider options you shared."
            ),
            tmdb_id=selected.tmdb_id,
            region=self._region(recommendation_request),
            language=recommendation_request.language,
        )

    def _fallback_recommendation(
        self,
        recommendation_request: RecommendationRequest,
        candidates: list[MovieCandidate],
    ) -> RecommendationResponse:
        selected = self._best_keyword_match(recommendation_request, candidates)
        region = self._region(recommendation_request)
        return RecommendationResponse(
            movie_title=selected.title,
            provider=", ".join(selected.provider_names),
            watch_link=selected.watch_link,
            reason=FALLBACK_REASONS[recommendation_request.language].format(region=region),
            tmdb_id=selected.tmdb_id,
            region=region,
            language=recommendation_request.language,
        )

    def _best_keyword_match(
        self,
        recommendation_request: RecommendationRequest,
        candidates: list[MovieCandidate],
    ) -> MovieCandidate:
        query = " ".join(
            part
            for part in [
                recommendation_request.mood,
                recommendation_request.group_context or "",
                recommendation_request.notes or "",
            ]
            if part
        ).lower()

        def score(candidate: MovieCandidate) -> tuple[int, float, int, float]:
            searchable = f"{candidate.title} {candidate.overview}".lower()
            keyword_score = sum(1 for word in query.split() if word in searchable)
            rating = candidate.rating or 0
            vote_count = candidate.vote_count or 0
            popularity = candidate.popularity or 0
            return keyword_score, rating, vote_count, popularity

        return max(candidates, key=score)

    def _candidate_by_title(
        self,
        candidates: list[MovieCandidate],
        title: str,
    ) -> MovieCandidate | None:
        normalized_title = title.strip().lower()
        for candidate in candidates:
            if candidate.title.lower() == normalized_title:
                return candidate
        return None

    def _region(self, recommendation_request: RecommendationRequest) -> str:
        return recommendation_request.region or self.settings.tmdb_region.upper()
