import json
import re

from openai import AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from app.config import Settings
from app.schemas import RecommendationRequest, RecommendationSearchPlan
from app.timing import StepTimer


SEARCH_PLAN_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "exact_title_queries": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
        },
        "similar_to_titles": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
        },
        "search_queries": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 6,
        },
        "genres": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 6,
        },
        "excluded_genres": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 6,
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
        },
        "excluded_keywords": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
        },
        "tones": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
        "themes": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
        "release_year_min": {"type": ["integer", "null"]},
        "release_year_max": {"type": ["integer", "null"]},
        "runtime_max_minutes": {"type": ["integer", "null"]},
        "original_language": {"type": ["string", "null"]},
        "strictness": {"type": "string", "enum": ["low", "medium", "high"]},
        "relax_quality": {"type": "boolean"},
        "rationale": {"type": "string"},
    },
    "required": [
        "exact_title_queries",
        "similar_to_titles",
        "search_queries",
        "genres",
        "excluded_genres",
        "keywords",
        "excluded_keywords",
        "tones",
        "themes",
        "release_year_min",
        "release_year_max",
        "runtime_max_minutes",
        "original_language",
        "strictness",
        "relax_quality",
        "rationale",
    ],
}

GENRE_TERMS = {
    "action",
    "adventure",
    "animation",
    "comedy",
    "crime",
    "documentary",
    "drama",
    "family",
    "fantasy",
    "history",
    "horror",
    "music",
    "mystery",
    "romance",
    "science fiction",
    "sci-fi",
    "scifi",
    "thriller",
    "war",
    "western",
}
NICHE_TERMS = {
    "a24",
    "arthouse",
    "cerebral",
    "cult",
    "experimental",
    "foreign",
    "indie",
    "low budget",
    "melancholy",
    "microbudget",
    "niche",
    "obscure",
    "quiet",
    "slow burn",
    "underrated",
}


class RecommendationPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def create_plan(
        self,
        recommendation_request: RecommendationRequest,
    ) -> RecommendationSearchPlan:
        timer = StepTimer(__name__, "llm_query_planning")
        fallback_plan = self._fallback_plan(recommendation_request)
        if not self.settings.openai_api_key:
            timer.mark("fallback_no_openai_key")
            timer.finish(
                relax_quality=fallback_plan.relax_quality,
                strictness=fallback_plan.strictness,
            )
            return fallback_plan

        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        try:
            response = await client.responses.create(
                model=self.settings.openai_model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "You convert a movie-night request into TMDb search planning "
                            "parameters. Do not choose the final movie. Extract title "
                            "queries, similarity references, genres, excluded genres, "
                            "keywords, tones, themes, era/runtime/language constraints, "
                            "and whether niche intent should relax quality thresholds. "
                            "Use concise English terms that map well to TMDb search. "
                            "Use exact_title_queries only when the user seems to want a "
                            "specific title; use similar_to_titles when a title is only a "
                            "reference. Set relax_quality true for niche, obscure, indie, "
                            "foreign-language, documentary, cult, or very specific mood/theme "
                            "requests where strict vote thresholds may hide good matches."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            recommendation_request.model_dump(mode="json")
                        ),
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "movie_search_plan",
                        "schema": SEARCH_PLAN_RESPONSE_SCHEMA,
                        "strict": True,
                    }
                },
            )
        except OpenAIError:
            timer.mark("fallback_openai_error")
            timer.finish(
                relax_quality=fallback_plan.relax_quality,
                strictness=fallback_plan.strictness,
            )
            return fallback_plan
        timer.mark("openai_response")

        try:
            payload = json.loads(self._response_text(response))
        except json.JSONDecodeError:
            timer.mark("fallback_invalid_json")
            timer.finish(
                relax_quality=fallback_plan.relax_quality,
                strictness=fallback_plan.strictness,
            )
            return fallback_plan

        try:
            plan = self._merge_with_fallback(payload, fallback_plan)
        except ValidationError:
            timer.mark("fallback_invalid_schema")
            timer.finish(
                relax_quality=fallback_plan.relax_quality,
                strictness=fallback_plan.strictness,
            )
            return fallback_plan
        timer.mark("validation")
        timer.finish(relax_quality=plan.relax_quality, strictness=plan.strictness)
        return plan

    def _fallback_plan(
        self,
        recommendation_request: RecommendationRequest,
    ) -> RecommendationSearchPlan:
        request_text = self._request_text(recommendation_request)
        normalized_text = request_text.lower()
        exact_titles = self._quoted_titles(request_text)
        similar_titles = self._similarity_titles(request_text)
        genres = [
            "science fiction" if term in {"sci-fi", "scifi"} else term
            for term in sorted(GENRE_TERMS)
            if term in normalized_text
        ]
        keywords = [
            word
            for word in self._content_words(normalized_text)
            if word not in genres
        ][:8]

        return RecommendationSearchPlan(
            exact_title_queries=[
                title for title in exact_titles if title not in similar_titles
            ],
            similar_to_titles=similar_titles,
            search_queries=[request_text[:120]] if request_text else [],
            genres=list(dict.fromkeys(genres)),
            keywords=keywords,
            tones=[
                term
                for term in sorted(NICHE_TERMS)
                if term in normalized_text
            ][:4],
            themes=keywords[:4],
            strictness="low" if self._is_niche_request(normalized_text) else "medium",
            relax_quality=self._is_niche_request(normalized_text),
            rationale="Deterministic fallback search plan.",
        )

    def _merge_with_fallback(
        self,
        payload: dict,
        fallback_plan: RecommendationSearchPlan,
    ) -> RecommendationSearchPlan:
        plan = RecommendationSearchPlan.model_validate(payload)
        return plan.model_copy(
            update={
                "exact_title_queries": self._coalesce_lists(
                    plan.exact_title_queries,
                    fallback_plan.exact_title_queries,
                ),
                "similar_to_titles": self._coalesce_lists(
                    plan.similar_to_titles,
                    fallback_plan.similar_to_titles,
                ),
                "search_queries": self._coalesce_lists(
                    plan.search_queries,
                    fallback_plan.search_queries,
                ),
                "genres": self._coalesce_lists(plan.genres, fallback_plan.genres),
                "keywords": self._coalesce_lists(plan.keywords, fallback_plan.keywords),
                "tones": self._coalesce_lists(plan.tones, fallback_plan.tones),
                "themes": self._coalesce_lists(plan.themes, fallback_plan.themes),
            }
        )

    def _coalesce_lists(self, primary: list[str], fallback: list[str]) -> list[str]:
        return list(dict.fromkeys([*primary, *fallback]))

    def _request_text(self, recommendation_request: RecommendationRequest) -> str:
        return " ".join(
            part
            for part in [
                recommendation_request.mood,
                recommendation_request.group_context or "",
                recommendation_request.notes or "",
            ]
            if part
        ).strip()

    def _quoted_titles(self, text: str) -> list[str]:
        return list(
            dict.fromkeys(
                part
                for quoted in re.findall(r'"([^"]{2,80})"|\'([^\']{2,80})\'', text)
                for part in quoted
                if part
            )
        )

    def _similarity_titles(self, text: str) -> list[str]:
        patterns = (
            r"\bsimilar(?:\s+(?:movie|film|movies|films))?\s+to\s+([^,.;:\n]+)",
            r"\b(?:something|anything|movie|film|one)\s+like\s+([^,.;:\n]+)",
            r"\bin the (?:same )?(?:vein|style|mood|vibe) as\s+([^,.;:\n]+)",
            r"\balong the lines of\s+([^,.;:\n]+)",
            r"\balgo\s+como\s+([^,.;:\n]+)",
            r"\bparecid[oa]s?\s+a\s+([^,.;:\n]+)",
        )
        matches: list[str] = []
        for pattern in patterns:
            matches.extend(
                match.group(1).strip(" \"'()[]{}!?")
                for match in re.finditer(pattern, text, flags=re.IGNORECASE)
            )
        return list(dict.fromkeys(match for match in matches if 2 <= len(match) <= 80))

    def _content_words(self, normalized_text: str) -> list[str]:
        ignored = {
            "about",
            "after",
            "also",
            "and",
            "but",
            "for",
            "from",
            "movie",
            "pelicula",
            "please",
            "something",
            "that",
            "the",
            "tonight",
            "watch",
            "with",
        }
        return list(
            dict.fromkeys(
                word
                for word in re.findall(r"[a-z]{4,}", normalized_text)
                if word not in ignored
            )
        )

    def _is_niche_request(self, normalized_text: str) -> bool:
        return any(term in normalized_text for term in NICHE_TERMS)

    def _response_text(self, response: object) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return str(output_text)

        output = getattr(response, "output", [])
        for item in output:
            if getattr(item, "type", None) != "message":
                continue
            for content in getattr(item, "content", []):
                if getattr(content, "type", None) == "output_text":
                    return str(getattr(content, "text", ""))
        return "{}"
