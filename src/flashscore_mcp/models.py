from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class Sport(BaseModel):
    name: str
    slug: str
    url: str


class Country(BaseModel):
    name: str
    slug: Optional[str] = None
    url: Optional[str] = None


class League(BaseModel):
    name: str
    slug: str
    url: str
    country: Optional[str] = None
    sport: Optional[str] = None


class StandingRow(BaseModel):
    position: int
    team: str
    section: Optional[str] = None
    played: Optional[int] = Field(None, description="MP")
    wins: Optional[int] = None
    losses: Optional[int] = None
    draws: Optional[int] = None
    table_points: Optional[int] = Field(None, description="Pts")
    form: Optional[str] = None
    extras: dict = Field(default_factory=dict)


class StandingSection(BaseModel):
    name: Optional[str] = None
    rows: list[StandingRow] = Field(default_factory=list)


class StandingsPage(BaseModel):
    kind: str = "table"
    sections: list[StandingSection] = Field(default_factory=list)
    available_seasons: list[str] = Field(default_factory=list)


class PeriodScore(BaseModel):
    label: str
    home: str
    away: str


class MatchResult(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    home_team: str
    away_team: str
    status: str = "finished"
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    extras: dict = Field(default_factory=dict)


class OddsPrice(BaseModel):
    bookmaker: Optional[str] = None
    side: str
    price: str


class LeagueInfo(BaseModel):
    name: str
    sport: Optional[str] = None
    country: Optional[str] = None
    season: Optional[str] = None
    url: Optional[str] = None
    tabs: list[str] = Field(default_factory=list)
    archive_seasons: list["Season"] = Field(default_factory=list)


class Fixture(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    home_team: str
    away_team: str
    url: Optional[str] = None


class NewsItem(BaseModel):
    title: str
    link: str
    date: Optional[str] = None
    summary: Optional[str] = None


class Season(BaseModel):
    name: str
    url: Optional[str] = None
    id: Optional[str] = None
    winner: Optional[str] = None
