"""Normalised stage and round fields next to Flashscore's raw labels.

Flashscore labels a row twice: the competition header ('USA: NFL',
'USA: NFL - Play Offs', 'USA: NFL - All Stars', 'USA: NFL - Pre-season') and
the round ('Round 7', 'Quarter-finals', 'Final'). The Pro Bowl is also
'Final', so the round alone cannot tell a Super Bowl from an all-star game;
the competition header decides the stage and the round only refines it.

stage is one of: regular_season, playoffs, all_star, preseason,
qualification, relegation, or None when nothing says.
"""
from __future__ import annotations

import re
from typing import Optional

_ALL_STAR = re.compile(r"all[\s-]?stars?|pro bowl|all-star game", re.I)
_PRESEASON = re.compile(r"pre[\s-]?season|hall of fame|exhibition|friendl", re.I)
_PLAYOFFS = re.compile(r"play[\s-]?offs?|post[\s-]?season|knockout|championship round", re.I)
_QUALIFY = re.compile(r"qualification|qualifying", re.I)
_RELEGATION = re.compile(r"relegation|promotion", re.I)
_REGULAR_TAIL = re.compile(r"regular season|league stage|main round|group stage", re.I)

_NUMBERED = re.compile(r"^(?:round|week|matchday|game ?week|md)\s*(\d{1,3})$", re.I)

# Generic knockout rounds (slug, ordinal from the final backwards).
_KNOCKOUT = (
    (re.compile(r"^1/64[\s-]*finals?$", re.I), "round_of_128"),
    (re.compile(r"^1/32[\s-]*finals?$", re.I), "round_of_64"),
    (re.compile(r"^1/16[\s-]*finals?$", re.I), "round_of_32"),
    (re.compile(r"^1/8[\s-]*finals?$|^round of 16$|^last 16$", re.I), "round_of_16"),
    (re.compile(r"^quarter[\s-]*finals?$|^1/4[\s-]*finals?$", re.I), "quarter_final"),
    (re.compile(r"^semi[\s-]*finals?$|^1/2[\s-]*finals?$", re.I), "semi_final"),
    (re.compile(r"^3rd place|^third place|^bronze", re.I), "third_place"),
    (re.compile(r"^finals?$|^grand final$", re.I), "final"),
    (re.compile(r"^wild ?card", re.I), "wild_card"),
    (re.compile(r"^divisional", re.I), "divisional"),
    (re.compile(r"^conference (?:finals?|championship)", re.I), "conference_final"),
    (re.compile(r"^super bowl", re.I), "final"),
)

# League-specific names for the generic slugs (competition prefix -> names).
_NAMED = {
    "usa: nfl": {
        "round_of_16": "Wild Card",
        "wild_card": "Wild Card",
        "quarter_final": "Divisional Round",
        "divisional": "Divisional Round",
        "semi_final": "Conference Championship",
        "conference_final": "Conference Championship",
        "final": "Super Bowl",
    },
}
_GENERIC_NAMES = {
    "round_of_128": "Round of 128",
    "round_of_64": "Round of 64",
    "round_of_32": "Round of 32",
    "round_of_16": "Round of 16",
    "quarter_final": "Quarter-final",
    "semi_final": "Semi-final",
    "third_place": "Third place",
    "final": "Final",
    "wild_card": "Wild Card",
    "divisional": "Divisional Round",
    "conference_final": "Conference Final",
}


def _clean(text: Optional[str]) -> str:
    return " ".join((text or "").split())


def _league_key(competition: str) -> str:
    """'USA: NFL - Play Offs' -> 'usa: nfl'."""
    return competition.split(" - ")[0].strip().lower()


def knockout_slug(round_label: Optional[str]) -> Optional[str]:
    text = _clean(round_label)
    for pattern, slug in _KNOCKOUT:
        if pattern.search(text):
            return slug
    return None


def round_number(round_label: Optional[str]) -> Optional[int]:
    found = _NUMBERED.match(_clean(round_label))
    return int(found.group(1)) if found else None


def classify(competition: Optional[str], round_label: Optional[str]) -> dict:
    """{stage, round_number, playoff_round, playoff_round_name} for one row."""
    comp = _clean(competition)
    rnd = _clean(round_label)
    tail = comp.split(" - ", 1)[1] if " - " in comp else ""
    number = round_number(rnd)
    slug = knockout_slug(rnd)
    stage: Optional[str] = None
    if _ALL_STAR.search(tail or comp):
        stage = "all_star"
    elif _PRESEASON.search(tail):
        stage = "preseason"
    elif _PLAYOFFS.search(tail):
        stage = "playoffs"
    elif _QUALIFY.search(tail):
        stage = "qualification"
    elif _RELEGATION.search(tail):
        stage = "relegation"
    elif comp and (not tail or _REGULAR_TAIL.search(tail)):
        if number is not None or not slug:
            stage = "regular_season"
        else:
            # A knockout round inside the main competition (cups, play-in).
            stage = "playoffs"
    elif number is not None:
        stage = "regular_season"
    elif slug:
        stage = "playoffs"
    out = {"stage": stage, "round_number": number, "playoff_round": None, "playoff_round_name": None}
    if stage == "playoffs" and slug:
        out["playoff_round"] = slug
        named = _NAMED.get(_league_key(comp), {})
        out["playoff_round_name"] = named.get(slug) or _GENERIC_NAMES.get(slug)
    return out


def apply_stage(game):
    """A copy of a MatchResult with the normalised fields filled in."""
    return game.model_copy(update=classify(game.competition, game.round))
