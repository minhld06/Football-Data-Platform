import { notFound } from "next/navigation";
import type {
  LeagueSummary,
  TeamProfile,
  LeagueStanding,
  TeamForm,
  MatchResult,
  PlayerProfile,
  PlayerPerformance,
  SearchResult,
} from "./types";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (res.status === 404) {
    notFound();
  }
  if (!res.ok) {
    throw new Error(`Backend request failed: ${res.status} ${path}`);
  }
  return res.json() as Promise<T>;
}

async function apiFetchOptional<T>(path: string): Promise<T | null> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (res.status === 404) {
    return null;
  }
  if (!res.ok) {
    throw new Error(`Backend request failed: ${res.status} ${path}`);
  }
  return res.json() as Promise<T>;
}

export function getLeagues() {
  return apiFetch<LeagueSummary[]>("/api/leagues");
}

export function getLeagueStandings(league: string, season?: string) {
  const query = season ? `?season=${encodeURIComponent(season)}` : "";
  return apiFetch<LeagueStanding[]>(`/api/leagues/${league}/standings${query}`);
}

export function getLeagueMatches(league: string, season?: string) {
  const query = season ? `?season=${encodeURIComponent(season)}` : "";
  return apiFetch<MatchResult[]>(`/api/leagues/${league}/matches${query}`);
}

export function getRecentMatches(limit = 5) {
  return apiFetch<MatchResult[]>(`/api/matches/recent?limit=${limit}`);
}

export function getTopScorers(limit = 5, league?: string) {
  const query = league ? `?league=${encodeURIComponent(league)}&limit=${limit}` : `?limit=${limit}`;
  return apiFetch<PlayerPerformance[]>(`/api/players/top-scorers${query}`);
}

export function getTeam(teamId: number) {
  return apiFetch<TeamProfile>(`/api/teams/${teamId}`);
}

export function getTeamMatches(teamId: number) {
  return apiFetch<MatchResult[]>(`/api/teams/${teamId}/matches`);
}

export function getTeamForm(teamId: number) {
  return apiFetchOptional<TeamForm>(`/api/teams/${teamId}/form`);
}

export function getPlayer(playerId: number) {
  return apiFetch<PlayerProfile>(`/api/players/${playerId}`);
}

export function getPlayerPerformance(playerId: number) {
  return apiFetch<PlayerPerformance>(`/api/players/${playerId}/performance`);
}

export function search(q: string) {
  return apiFetch<SearchResult[]>(`/api/search?q=${encodeURIComponent(q)}`);
}