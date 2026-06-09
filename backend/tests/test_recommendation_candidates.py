import unittest

from app.config import Settings
from app.schemas import MovieCandidate, Provider, RecommendationRequest
from app.services.llm import RecommendationEngine
from app.services.tmdb import TMDbClient


def make_client(**overrides: object) -> TMDbClient:
    settings_values = {
        "tmdb_api_key": "test-key",
        "tmdb_min_vote_average": 7.0,
        "tmdb_min_vote_count": 500,
        "tmdb_candidate_limit": 60,
        **overrides,
    }
    settings = Settings(**settings_values)
    return TMDbClient(settings)


def make_request(mood: str) -> RecommendationRequest:
    return RecommendationRequest(
        providers=[Provider.netflix],
        mood=mood,
        region="GB",
        language="en",
    )


def make_candidate(
    tmdb_id: int,
    title: str,
    release_year: str,
    rating: float,
    vote_count: int,
    popularity: float,
) -> MovieCandidate:
    return MovieCandidate(
        tmdb_id=tmdb_id,
        title=title,
        overview=f"{title} overview",
        release_year=release_year,
        rating=rating,
        vote_count=vote_count,
        popularity=popularity,
        provider_names=["Netflix"],
        watch_link=f"https://www.themoviedb.org/movie/{tmdb_id}/watch?locale=GB",
    )


class TMDbCandidateTests(unittest.TestCase):
    def test_extracts_title_reference_and_classic_intent(self) -> None:
        client = make_client()
        request = make_request("Casablanca, masterpiece, cinema classic")

        self.assertEqual(client._reference_queries(request), ["Casablanca"])
        self.assertTrue(client._has_classic_intent(request))

    def test_extracts_reference_without_searching_whole_like_phrase(self) -> None:
        client = make_client()
        request = make_request("Something like Casablanca for tonight")

        self.assertEqual(client._reference_queries(request), ["Casablanca"])
        self.assertEqual(client._similarity_reference_queries(request), ["Casablanca"])

    def test_extracts_similarity_reference_with_introductory_fillers(self) -> None:
        client = make_client()
        request = make_request(
            "Can I see a similar movie to let's say for instance Shutter Island?"
        )

        self.assertEqual(client._reference_queries(request), ["Shutter Island"])
        self.assertEqual(client._similarity_reference_queries(request), ["Shutter Island"])

    def test_rejects_generic_mood_as_title_reference(self) -> None:
        client = make_client()
        request = make_request("Funny tense thriller")

        self.assertEqual(client._reference_queries(request), [])

    def test_quality_thresholds_are_strict_by_default(self) -> None:
        client = make_client()

        self.assertFalse(
            client._passes_quality_threshold(
                {"id": 1, "vote_average": 6.9, "vote_count": 2000}
            )
        )
        self.assertFalse(
            client._passes_quality_threshold(
                {"id": 2, "vote_average": 7.5, "vote_count": 499}
            )
        )
        self.assertTrue(
            client._passes_quality_threshold(
                {"id": 3, "vote_average": 7.0, "vote_count": 500}
            )
        )

    def test_classic_intent_adds_classic_discover_pool(self) -> None:
        client = make_client()
        params = client._discover_param_sets(
            make_request("cinema classic masterpiece"),
            "GB",
            [8],
            "en-GB",
        )

        self.assertEqual(params[0]["primary_release_date.lte"], "2000-12-31")
        self.assertEqual(params[0]["sort_by"], "vote_average.desc")
        self.assertGreaterEqual(params[0]["vote_count.gte"], 1000)
        self.assertEqual(params[1]["sort_by"], "popularity.desc")

    def test_classic_ranking_prefers_old_acclaimed_films_over_new_popularity(
        self,
    ) -> None:
        client = make_client()
        request = make_request("Casablanca, masterpiece, cinema classic")
        candidates = [
            make_candidate(999, "Swapped", "2026", 7.4, 1200, 900.0),
            make_candidate(289, "Casablanca", "1942", 8.2, 5500, 40.0),
        ]

        ranked = client._rank_and_limit_candidates(candidates, request, 60)

        self.assertEqual(ranked[0].title, "Casablanca")

    def test_similarity_ranking_excludes_reference_title(self) -> None:
        client = make_client()
        request = make_request("Something similar to Shutter Island")
        candidates = [
            make_candidate(11324, "Shutter Island", "2010", 8.2, 24000, 80.0),
            make_candidate(146233, "Prisoners", "2013", 8.1, 12000, 65.0),
        ]

        ranked = client._rank_and_limit_candidates(candidates, request, 60)

        self.assertEqual([candidate.title for candidate in ranked], ["Prisoners"])

    def test_similarity_ranking_excludes_seed_id_for_misspelled_reference(
        self,
    ) -> None:
        client = make_client()
        request = make_request("similar movie to Shattered Island")
        candidates = [
            make_candidate(11324, "Shutter Island", "2010", 8.2, 24000, 80.0),
            make_candidate(146233, "Prisoners", "2013", 8.1, 12000, 65.0),
        ]

        ranked = client._rank_and_limit_candidates(
            candidates,
            request,
            60,
            excluded_tmdb_ids={11324},
        )

        self.assertEqual([candidate.title for candidate in ranked], ["Prisoners"])

    def test_candidate_limit_is_capped_for_llm_prompt_size(self) -> None:
        client = make_client(tmdb_candidate_limit=1000)

        self.assertEqual(client._candidate_limit(), 100)


class FallbackRecommendationTests(unittest.TestCase):
    def test_fallback_prefers_classic_match_over_new_popularity(self) -> None:
        engine = RecommendationEngine(Settings(openai_api_key=None))
        request = make_request("masterpiece cinema classic")
        candidates = [
            make_candidate(999, "Swapped", "2026", 7.4, 1200, 900.0),
            make_candidate(238, "The Godfather", "1972", 8.7, 20000, 80.0),
        ]

        selected = engine._best_keyword_match(request, candidates)

        self.assertEqual(selected.title, "The Godfather")


if __name__ == "__main__":
    unittest.main()
