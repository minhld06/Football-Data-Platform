export interface LeagueSummary {
  league: string;
  seasons: string[];
}

export interface TeamSummary {
  team_id: number;
  team_name: string;
  team_short_name: string | null;
  team_tla: string | null;
}

export interface TeamProfile extends TeamSummary {
  league: string;
}

export interface LeagueStanding {
  league: string;
  season: string;
  team_id: number;
  team_name: string;
  team_short_name: string | null;
  team_tla: string | null;
  position: number;
  played_games: number;
  won: number;
  draw: number;
  lost: number;
  points: number;
  goals_for: number;
  goals_against: number;
  goal_difference: number;
  form: string | null;
  xg: number | null;
  xga: number | null;
  xpts: number | null;
}

export interface TeamForm {
  league: string;
  season: string;
  team_id: number;
  team_name: string;
  matches_played: number;
  wins: number;
  draws: number;
  losses: number;
  points: number;
  goals_for: number;
  goals_against: number;
  form: string;
}

export interface MatchResult {
  source_match_id: number;
  league: string;
  season: string;
  matchday: number | null;
  status: string;
  utc_date: string;
  home_team_id: number;
  home_team_name: string | null;
  away_team_id: number;
  away_team_name: string | null;
  home_score: number | null;
  away_score: number | null;
}

export interface PlayerProfile {
  player_id: number;
  player_name: string;
  position: string | null;
  nationality: string | null;
  date_of_birth: string | null;
  age: number | null;
  shirt_number: number | null;
  team_id: number | null;
  team_name: string | null;
  parent_team_id: number | null;
  parent_team_name: string | null;
  is_on_loan: boolean;
  league: string;
}

export interface PlayerPerformance {
  player_id: number;
  player_name: string;
  team_id: number;
  team_name: string | null;
  league: string;
  goals: number | null;
  assists: number | null;
  apps: number | null;
  minutes: number | null;
  xg: number | null;
  xa: number | null;
  xg90: number | null;
  xa90: number | null;
}

export interface SearchResult {
  type: "team" | "player";
  id: number;
  name: string;
  subtitle: string | null;
}