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

FALLBACK_WHY_RECOMMENDED = {
    "en": (
        "It is available in {region} from your selected providers and scored best "
        "against the mood, group, and notes you shared."
    ),
    "es": (
        "Está disponible en {region} en las plataformas seleccionadas y fue la "
        "mejor coincidencia con el ambiente, el grupo y las notas que compartiste."
    ),
}
CLASSIC_INTENT_TERMS = (
    "classic",
    "classics",
    "cinema classic",
    "movie classic",
    "film classic",
    "masterpiece",
    "masterpieces",
    "old hollywood",
    "golden age",
    "timeless",
    "canonical",
    "canon",
    "acclaimed",
    "obra maestra",
    "clásico",
    "clásicos",
    "cine clásico",
    "película clásica",
    "clasico",
    "clasicos",
    "cine clasico",
    "pelicula clasica",
)


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
                            "Interpret the user's intent semantically in any language. "
                            "When the user asks for something similar, like, comparable, "
                            "parecido, similar a, algo como, del estilo de, or equivalent "
                            "wording around a named title, treat that title only as a "
                            "reference and choose a different candidate with a close tonal, "
                            "genre, era, or reputation match. Never choose the reference "
                            "title itself in that case, including spelling, casing, "
                            "punctuation, translation, or minor-misspelling variants of "
                            "that title. If the user names a specific title as the movie "
                            "they want and not merely as a similarity reference, strongly "
                            "prefer that exact title when it is in the candidate list. If "
                            "the named title is not available, choose a close match. "
                            "Favor well-rated candidates with stronger vote counts and popularity. "
                            "For classic, masterpiece, or cinema-canon requests, prioritize "
                            "older, highly rated, widely voted films over new releases. "
                            "Respect the user's allow_extra_costs preference when explaining the choice. "
                            "Return JSON only with movie_title, provider, watch_link, reason, "
                            "and why_recommended. Use reason as a short summary. "
                            "Use why_recommended to explain in one or two sentences why this "
                            "movie fits the user's mood, group context, notes, selected providers, "
                            "region, and extra-cost preference. "
                            "Write reason and why_recommended in "
                            f"{LANGUAGE_LABELS[recommendation_request.language]}. "
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

        fallback_reason = FALLBACK_REASONS[recommendation_request.language].format(
            region=self._region(recommendation_request),
        )
        reason = self._clean_text(llm_payload.get("reason")) or fallback_reason
        why_recommended = (
            self._clean_text(llm_payload.get("why_recommended"))
            or reason
        )

        return RecommendationResponse(
            movie_title=selected.title,
            provider=str(llm_payload.get("provider") or ", ".join(selected.provider_names)),
            watch_link=selected.watch_link,
            reason=reason,
            why_recommended=why_recommended,
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
            why_recommended=FALLBACK_WHY_RECOMMENDED[
                recommendation_request.language
            ].format(region=region),
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

        has_classic_intent = self._has_classic_intent(query)

        def score(candidate: MovieCandidate) -> tuple[int, int, float, int, float]:
            searchable = f"{candidate.title} {candidate.overview}".lower()
            keyword_score = sum(1 for word in query.split() if word in searchable)
            classic_score = int(
                has_classic_intent
                and candidate.release_year is not None
                and self._release_year(candidate.release_year) is not None
                and self._release_year(candidate.release_year) <= 2000
            )
            rating = candidate.rating or 0
            vote_count = candidate.vote_count or 0
            popularity = candidate.popularity or 0
            return keyword_score, classic_score, rating, vote_count, popularity

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

    def _clean_text(self, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _region(self, recommendation_request: RecommendationRequest) -> str:
        return recommendation_request.region or self.settings.tmdb_region.upper()

    def _has_classic_intent(self, query: str) -> bool:
        return any(term in query for term in CLASSIC_INTENT_TERMS)

    def _release_year(self, release_year: str) -> int | None:
        try:
            return int(release_year)
        except ValueError:
            return None
