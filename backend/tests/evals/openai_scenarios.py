"""OpenAI recommendation eval scenarios.

These fixtures exercise the exact request shape sent to the OpenAI chat
completion API by ``RecommendationEngine``: region, user answers, and candidate
movies. They are intentionally deterministic so live model responses can be
compared across runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas import MovieCandidate, RecommendationRequest


@dataclass(frozen=True)
class OpenAIScenario:
    id: str
    description: str
    request: dict[str, Any]
    candidate_ids: tuple[str, ...]


CANDIDATE_LIBRARY: dict[str, MovieCandidate] = {
    "paddington-2": MovieCandidate(
        tmdb_id=346648,
        title="Paddington 2",
        overview=(
            "A kind bear settles into London life, searches for the perfect gift, "
            "and turns a wrongful accusation into a warm adventure."
        ),
        release_year="2017",
        rating=7.5,
        provider_names=["Netflix"],
        watch_link="https://www.themoviedb.org/movie/346648/watch?locale=GB",
    ),
    "knives-out": MovieCandidate(
        tmdb_id=546554,
        title="Knives Out",
        overview=(
            "A detective investigates a wealthy family's secrets after the death "
            "of a crime novelist."
        ),
        release_year="2019",
        rating=7.8,
        provider_names=["Netflix"],
        watch_link="https://www.themoviedb.org/movie/546554/watch?locale=GB",
    ),
    "the-social-network": MovieCandidate(
        tmdb_id=37799,
        title="The Social Network",
        overview=(
            "An ambitious student builds a social media empire while friendships "
            "and loyalties fracture."
        ),
        release_year="2010",
        rating=7.4,
        provider_names=["Netflix"],
        watch_link="https://www.themoviedb.org/movie/37799/watch?locale=GB",
    ),
    "the-mitchells-vs-the-machines": MovieCandidate(
        tmdb_id=501929,
        title="The Mitchells vs. the Machines",
        overview=(
            "A chaotic family road trip becomes a mission to save the world from "
            "a robot uprising."
        ),
        release_year="2021",
        rating=7.9,
        provider_names=["Netflix"],
        watch_link="https://www.themoviedb.org/movie/501929/watch?locale=GB",
    ),
    "spider-verse": MovieCandidate(
        tmdb_id=324857,
        title="Spider-Man: Into the Spider-Verse",
        overview=(
            "Teen Miles Morales becomes Spider-Man and joins heroes from across "
            "the multiverse."
        ),
        release_year="2018",
        rating=8.4,
        provider_names=["Disney+"],
        watch_link="https://www.themoviedb.org/movie/324857/watch?locale=GB",
    ),
    "wall-e": MovieCandidate(
        tmdb_id=10681,
        title="WALL-E",
        overview=(
            "A lonely waste-collecting robot discovers love and hope on an "
            "abandoned Earth."
        ),
        release_year="2008",
        rating=8.1,
        provider_names=["Disney+"],
        watch_link="https://www.themoviedb.org/movie/10681/watch?locale=GB",
    ),
    "moana": MovieCandidate(
        tmdb_id=277834,
        title="Moana",
        overview=(
            "A courageous wayfinder sails beyond her island to restore balance "
            "with the help of a demigod."
        ),
        release_year="2016",
        rating=7.6,
        provider_names=["Disney+"],
        watch_link="https://www.themoviedb.org/movie/277834/watch?locale=GB",
    ),
    "soul": MovieCandidate(
        tmdb_id=508442,
        title="Soul",
        overview=(
            "A jazz pianist travels through cosmic realms and reconsiders what "
            "makes life meaningful."
        ),
        release_year="2020",
        rating=8.1,
        provider_names=["Disney+"],
        watch_link="https://www.themoviedb.org/movie/508442/watch?locale=GB",
    ),
    "interstellar": MovieCandidate(
        tmdb_id=157336,
        title="Interstellar",
        overview=(
            "Explorers travel through a wormhole in space in an attempt to ensure "
            "humanity's survival."
        ),
        release_year="2014",
        rating=8.5,
        provider_names=["YouTube"],
        watch_link="https://www.themoviedb.org/movie/157336/watch?locale=GB",
    ),
    "arrival": MovieCandidate(
        tmdb_id=329865,
        title="Arrival",
        overview=(
            "A linguist helps communicate with mysterious visitors and faces a "
            "deeply emotional choice."
        ),
        release_year="2016",
        rating=7.6,
        provider_names=["YouTube"],
        watch_link="https://www.themoviedb.org/movie/329865/watch?locale=GB",
    ),
    "mad-max-fury-road": MovieCandidate(
        tmdb_id=76341,
        title="Mad Max: Fury Road",
        overview=(
            "Survivors race across a post-apocalyptic wasteland in a relentless "
            "action chase."
        ),
        release_year="2015",
        rating=7.6,
        provider_names=["YouTube"],
        watch_link="https://www.themoviedb.org/movie/76341/watch?locale=GB",
    ),
    "the-big-sick": MovieCandidate(
        tmdb_id=416477,
        title="The Big Sick",
        overview=(
            "A comedian navigates romance, family expectations, and a frightening "
            "medical crisis."
        ),
        release_year="2017",
        rating=7.3,
        provider_names=["YouTube"],
        watch_link="https://www.themoviedb.org/movie/416477/watch?locale=GB",
    ),
    "dune": MovieCandidate(
        tmdb_id=438631,
        title="Dune",
        overview=(
            "A young heir enters a dangerous desert world of prophecy, politics, "
            "and giant sandworms."
        ),
        release_year="2021",
        rating=7.8,
        provider_names=["HBO / NOW"],
        watch_link="https://www.themoviedb.org/movie/438631/watch?locale=GB",
    ),
    "inception": MovieCandidate(
        tmdb_id=27205,
        title="Inception",
        overview=(
            "A skilled thief enters layered dreams to plant an idea in a target's "
            "mind."
        ),
        release_year="2010",
        rating=8.4,
        provider_names=["HBO / NOW"],
        watch_link="https://www.themoviedb.org/movie/27205/watch?locale=GB",
    ),
    "barbie": MovieCandidate(
        tmdb_id=346698,
        title="Barbie",
        overview=(
            "A doll leaves a perfect pink world for a funny and self-aware trip "
            "through real-world identity."
        ),
        release_year="2023",
        rating=7.0,
        provider_names=["HBO / NOW"],
        watch_link="https://www.themoviedb.org/movie/346698/watch?locale=GB",
    ),
    "the-batman": MovieCandidate(
        tmdb_id=414906,
        title="The Batman",
        overview=(
            "A brooding detective hunts a serial killer and uncovers corruption "
            "through Gotham City."
        ),
        release_year="2022",
        rating=7.7,
        provider_names=["HBO / NOW"],
        watch_link="https://www.themoviedb.org/movie/414906/watch?locale=GB",
    ),
}


SCENARIOS: tuple[OpenAIScenario, ...] = (
    OpenAIScenario(
        id="netflix-light-date-night",
        description="Netflix-only request for a warm, low-friction date-night film.",
        request={
            "providers": ["netflix"],
            "mood": "Light, charming, and easy to agree on",
            "group_context": "Date night after a long workday",
            "notes": "Avoid anything bleak or violent.",
        },
        candidate_ids=("paddington-2", "knives-out", "the-social-network"),
    ),
    OpenAIScenario(
        id="netflix-clever-mystery",
        description="Netflix-only request that should favor a witty mystery.",
        request={
            "providers": ["netflix"],
            "mood": "Clever, twisty, but still fun",
            "group_context": "Two adults who like solving the puzzle as they watch",
            "notes": "No superhero movies tonight.",
        },
        candidate_ids=("paddington-2", "knives-out", "the-mitchells-vs-the-machines"),
    ),
    OpenAIScenario(
        id="netflix-family-animation",
        description="Netflix family-night request with animated and adult options.",
        request={
            "providers": ["netflix"],
            "mood": "Fast, funny, colorful family adventure",
            "group_context": "Parents and two kids under 12",
            "notes": "Keep it upbeat and not too scary.",
        },
        candidate_ids=("the-mitchells-vs-the-machines", "the-social-network", "knives-out"),
    ),
    OpenAIScenario(
        id="netflix-focused-drama",
        description="Netflix request for a sharp modern drama.",
        request={
            "providers": ["netflix"],
            "mood": "Smart, modern, dialogue-driven drama",
            "group_context": "One viewer wants something based on real events",
            "notes": "Prefer tech or business themes.",
        },
        candidate_ids=("the-social-network", "paddington-2", "knives-out"),
    ),
    OpenAIScenario(
        id="disney-superhero-energy",
        description="Disney+ request for kinetic superhero fun.",
        request={
            "providers": ["disney"],
            "mood": "High-energy, visually inventive superhero adventure",
            "group_context": "Teen cousins visiting",
            "notes": "Animation is welcome.",
        },
        candidate_ids=("spider-verse", "wall-e", "soul"),
    ),
    OpenAIScenario(
        id="disney-gentle-sci-fi",
        description="Disney+ request for gentle science fiction with heart.",
        request={
            "providers": ["disney"],
            "mood": "Quiet, hopeful, and emotional science fiction",
            "group_context": "Solo rewatch on a rainy evening",
            "notes": "No intense battles.",
        },
        candidate_ids=("wall-e", "spider-verse", "moana"),
    ),
    OpenAIScenario(
        id="disney-musical-adventure",
        description="Disney+ request for a musical adventure.",
        request={
            "providers": ["disney"],
            "mood": "A big-hearted musical adventure",
            "group_context": "Family sing-along night",
            "notes": "Prefer bright scenery and memorable songs.",
        },
        candidate_ids=("moana", "soul", "wall-e"),
    ),
    OpenAIScenario(
        id="disney-reflective-adult-animation",
        description="Disney+ request that asks for an introspective animated pick.",
        request={
            "providers": ["disney"],
            "mood": "Reflective, soulful, and a little philosophical",
            "group_context": "Adults who still love animation",
            "notes": "Something meaningful rather than loud.",
        },
        candidate_ids=("soul", "spider-verse", "moana"),
    ),
    OpenAIScenario(
        id="youtube-cerebral-sci-fi",
        description="YouTube request for thoughtful science fiction.",
        request={
            "providers": ["youtube"],
            "mood": "Cerebral, emotional science fiction",
            "group_context": "Two friends who want to discuss the ending",
            "notes": "Prefer ideas over explosions.",
        },
        candidate_ids=("arrival", "interstellar", "mad-max-fury-road"),
    ),
    OpenAIScenario(
        id="youtube-epic-space",
        description="YouTube request for a large-scale space epic.",
        request={
            "providers": ["youtube"],
            "mood": "Epic, awe-inspiring, and space-focused",
            "group_context": "Movie night with a big TV and sound system",
            "notes": "We are fine with a longer runtime.",
        },
        candidate_ids=("interstellar", "arrival", "the-big-sick"),
    ),
    OpenAIScenario(
        id="youtube-action-rush",
        description="YouTube request for a relentless action film.",
        request={
            "providers": ["youtube"],
            "mood": "Pure adrenaline and practical action",
            "group_context": "Friends want something loud",
            "notes": "Minimal setup, maximum momentum.",
        },
        candidate_ids=("mad-max-fury-road", "arrival", "the-big-sick"),
    ),
    OpenAIScenario(
        id="youtube-romantic-comedy",
        description="YouTube request for sincere romantic comedy.",
        request={
            "providers": ["youtube"],
            "mood": "Funny, romantic, sincere, and not too glossy",
            "group_context": "Couple looking for something grounded",
            "notes": "No space travel or car chases.",
        },
        candidate_ids=("the-big-sick", "interstellar", "mad-max-fury-road"),
    ),
    OpenAIScenario(
        id="hbo-prestige-sci-fi",
        description="HBO/NOW request for serious, immersive science fiction.",
        request={
            "providers": ["hbo"],
            "mood": "Grand, immersive, serious science fiction",
            "group_context": "Three adults who like world-building",
            "notes": "Prefer something visually spectacular.",
        },
        candidate_ids=("dune", "barbie", "the-batman"),
    ),
    OpenAIScenario(
        id="hbo-mind-bending-thriller",
        description="HBO/NOW request for a puzzle-box thriller.",
        request={
            "providers": ["hbo"],
            "mood": "Mind-bending thriller with a big concept",
            "group_context": "Friends who like Nolan movies",
            "notes": "Avoid superhero detective stories.",
        },
        candidate_ids=("inception", "the-batman", "barbie"),
    ),
    OpenAIScenario(
        id="hbo-pop-comedy",
        description="HBO/NOW request for bright social comedy.",
        request={
            "providers": ["hbo"],
            "mood": "Funny, colorful, satirical, and modern",
            "group_context": "Group wants something playful",
            "notes": "No dark crime tonight.",
        },
        candidate_ids=("barbie", "the-batman", "dune"),
    ),
    OpenAIScenario(
        id="hbo-dark-detective",
        description="HBO/NOW request for a dark detective story.",
        request={
            "providers": ["hbo"],
            "mood": "Dark, moody detective mystery",
            "group_context": "One viewer wants noir atmosphere",
            "notes": "Superhero elements are okay if the tone is grounded.",
        },
        candidate_ids=("the-batman", "barbie", "inception"),
    ),
    OpenAIScenario(
        id="netflix-disney-kids-choice",
        description="Netflix and Disney+ request for kids choosing together.",
        request={
            "providers": ["netflix", "disney"],
            "mood": "Funny animated adventure with heart",
            "group_context": "Three kids need to agree quickly",
            "notes": "Avoid anything too sad.",
        },
        candidate_ids=("the-mitchells-vs-the-machines", "moana", "soul", "knives-out"),
    ),
    OpenAIScenario(
        id="netflix-disney-comfort",
        description="Netflix and Disney+ request for a comforting film.",
        request={
            "providers": ["netflix", "disney"],
            "mood": "Comforting, kind, and optimistic",
            "group_context": "Recovering from a stressful week",
            "notes": "No villains who feel too realistic.",
        },
        candidate_ids=("paddington-2", "wall-e", "the-social-network", "spider-verse"),
    ),
    OpenAIScenario(
        id="netflix-youtube-grownup-laughs",
        description="Netflix and YouTube request for grounded adult comedy.",
        request={
            "providers": ["netflix", "youtube"],
            "mood": "Grown-up laughs with real emotion",
            "group_context": "Double date",
            "notes": "No animated movies.",
        },
        candidate_ids=("the-big-sick", "paddington-2", "the-mitchells-vs-the-machines", "arrival"),
    ),
    OpenAIScenario(
        id="netflix-youtube-tense-without-horror",
        description="Netflix and YouTube request for tension without horror.",
        request={
            "providers": ["netflix", "youtube"],
            "mood": "Tense and gripping but not horror",
            "group_context": "Adults after dinner",
            "notes": "We want suspense, not gore.",
        },
        candidate_ids=("knives-out", "arrival", "mad-max-fury-road", "paddington-2"),
    ),
    OpenAIScenario(
        id="disney-hbo-visual-spectacle",
        description="Disney+ and HBO/NOW request for visual spectacle.",
        request={
            "providers": ["disney", "hbo"],
            "mood": "Visually spectacular and transportive",
            "group_context": "Testing a new projector",
            "notes": "Story can be serious or adventurous.",
        },
        candidate_ids=("dune", "spider-verse", "wall-e", "barbie"),
    ),
    OpenAIScenario(
        id="disney-hbo-noir-vs-optimism",
        description="Disney+ and HBO/NOW request with mixed dark and hopeful cues.",
        request={
            "providers": ["disney", "hbo"],
            "mood": "Moody but not hopeless",
            "group_context": "One person wants dark, another wants some optimism",
            "notes": "Avoid pure comedy.",
        },
        candidate_ids=("the-batman", "wall-e", "soul", "inception"),
    ),
    OpenAIScenario(
        id="youtube-hbo-long-epic",
        description="YouTube and HBO/NOW request where runtime is acceptable.",
        request={
            "providers": ["youtube", "hbo"],
            "mood": "Long, epic, and immersive",
            "group_context": "Saturday night with no early plans",
            "notes": "Science fiction preferred.",
        },
        candidate_ids=("interstellar", "dune", "inception", "the-big-sick"),
    ),
    OpenAIScenario(
        id="youtube-hbo-shorter-crowd-pleaser",
        description="YouTube and HBO/NOW request for a crowd pleaser over dense sci-fi.",
        request={
            "providers": ["youtube", "hbo"],
            "mood": "Accessible, funny, and easy to jump into",
            "group_context": "Mixed group chatting while watching",
            "notes": "Avoid dense sci-fi mythology.",
        },
        candidate_ids=("barbie", "the-big-sick", "dune", "arrival"),
    ),
    OpenAIScenario(
        id="all-providers-single-best-family",
        description="All-provider request focused on family suitability.",
        request={
            "providers": ["netflix", "disney", "youtube", "hbo"],
            "mood": "Family-safe, funny, and genuinely good",
            "group_context": "Grandparents, parents, and kids",
            "notes": "No heavy violence or cynical ending.",
        },
        candidate_ids=("paddington-2", "moana", "barbie", "mad-max-fury-road"),
    ),
    OpenAIScenario(
        id="all-providers-ambiguous-good-movie",
        description="All-provider request with intentionally vague mood.",
        request={
            "providers": ["netflix", "disney", "youtube", "hbo"],
            "mood": "Just something good",
            "group_context": "Nobody can decide",
            "notes": "Pick the safest crowd-pleaser.",
        },
        candidate_ids=("spider-verse", "knives-out", "interstellar", "barbie"),
    ),
    OpenAIScenario(
        id="all-providers-no-animation",
        description="All-provider request that excludes animation.",
        request={
            "providers": ["netflix", "disney", "youtube", "hbo"],
            "mood": "Smart and gripping",
            "group_context": "Adults only",
            "notes": "No animation tonight.",
        },
        candidate_ids=("spider-verse", "knives-out", "arrival", "inception"),
    ),
    OpenAIScenario(
        id="all-providers-animation-required",
        description="All-provider request that explicitly asks for animation.",
        request={
            "providers": ["netflix", "disney", "youtube", "hbo"],
            "mood": "Inventive animation with emotional payoff",
            "group_context": "Animation fans",
            "notes": "Prefer something visually distinct.",
        },
        candidate_ids=("spider-verse", "wall-e", "the-mitchells-vs-the-machines", "barbie"),
    ),
    OpenAIScenario(
        id="all-providers-contradictory-notes",
        description="All-provider request with contradictory guidance.",
        request={
            "providers": ["netflix", "disney", "youtube", "hbo"],
            "mood": "Dark but comforting, intense but relaxing",
            "group_context": "Tired group with split preferences",
            "notes": "Avoid violence, but suspense is okay.",
        },
        candidate_ids=("the-batman", "paddington-2", "arrival", "soul"),
    ),
    OpenAIScenario(
        id="single-candidate-control",
        description="Control scenario where there is only one valid candidate.",
        request={
            "providers": ["youtube"],
            "mood": "Any thoughtful science fiction film",
            "group_context": "One viewer",
            "notes": "There is only one candidate, so select it.",
        },
        candidate_ids=("arrival",),
    ),
)


def build_request(scenario: OpenAIScenario) -> RecommendationRequest:
    return RecommendationRequest(**scenario.request)


def build_candidates(scenario: OpenAIScenario) -> list[MovieCandidate]:
    return [CANDIDATE_LIBRARY[candidate_id] for candidate_id in scenario.candidate_ids]


def build_openai_user_payload(scenario: OpenAIScenario, region: str = "GB") -> dict[str, Any]:
    request = build_request(scenario)
    candidates = build_candidates(scenario)
    return {
        "region": region,
        "user_answers": request.model_dump(mode="json"),
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }
