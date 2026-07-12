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
    played: int = Field(..., description="MP")
    wins: int
    losses: int
    draws: Optional[int] = None
    pf: float | int = Field(..., description="Points For")
    pa: float | int = Field(..., description="Points Against")
    pd: Optional[float | int] = None
    points: Optional[int] = None
    form: Optional[str] = None


class MatchResult(BaseModel):
    date: Optional[str] = None
    home_team: str
    away_team: str
    home_pf: float | int
    away_pf: float | int


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
