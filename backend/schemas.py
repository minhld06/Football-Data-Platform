from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class LeagueSummary(BaseModel):
    league: str
    seasons: list[str]


class TeamSummary(BaseModel):
    team_id: int
    team_name: str
    team_short_name: Optional[str] = None
    team_tla: Optional[str] = None


class TeamProfile(TeamSummary):
    league: str


class LeagueStanding(BaseModel):
    league: str
    season: str
    team_id: int
    team_name: str
    team_short_name: Optional[str] = None
    team_tla: Optional[str] = None
    position: int
    played_games: int
    won: int
    draw: int
    lost: int
    points: int
    goals_for: int
    goals_against: int
    goal_difference: int
    form: Optional[str] = None
    xg: Optional[float] = None
    xga: Optional[float] = None
    xpts: Optional[float] = None


class TeamForm(BaseModel):
    league: str
    season: str
    team_id: int
    team_name: str
    matches_played: int
    wins: int
    draws: int
    losses: int
    points: int
    goals_for: int
    goals_against: int
    form: str


class MatchResult(BaseModel):
    source_match_id: int
    league: str
    season: str
    matchday: Optional[int] = None
    status: str
    utc_date: datetime
    home_team_id: int
    home_team_name: Optional[str] = None
    away_team_id: int
    away_team_name: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class PlayerProfile(BaseModel):
    player_id: int
    player_name: str
    position: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[date] = None
    age: Optional[int] = None
    shirt_number: Optional[int] = None
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    parent_team_id: Optional[int] = None
    parent_team_name: Optional[str] = None
    is_on_loan: bool = False
    league: str


class PlayerPerformance(BaseModel):
    player_id: int
    player_name: str
    season: str
    team_id: int
    team_name: Optional[str] = None
    league: str
    goals: Optional[int] = None
    assists: Optional[int] = None
    apps: Optional[int] = None
    minutes: Optional[int] = None
    xg: Optional[float] = None
    xa: Optional[float] = None
    xg90: Optional[float] = None
    xa90: Optional[float] = None


class SearchResult(BaseModel):
    type: str
    id: int
    name: str
    subtitle: Optional[str] = None