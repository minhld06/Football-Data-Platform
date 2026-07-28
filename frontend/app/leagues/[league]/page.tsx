import { notFound } from "next/navigation";
import StandingsTable from "@/components/StandingsTable";
import MatchList from "@/components/MatchList";
import SeasonSelect from "@/components/SeasonSelect";
import { getLeagues, getLeagueStandings, getLeagueMatches, getTopScorers } from "@/lib/api";

const LEAGUE_LABELS: Record<string, string> = {
  "premier-league": "Premier League",
  "ligue-1": "Ligue 1",
};

export default async function LeaguePage({
  params,
  searchParams,
}: {
  params: Promise<{ league: string }>;
  searchParams: Promise<{ season?: string }>;
}) {
  const { league } = await params;
  const { season: seasonParam } = await searchParams;

  const leagues = await getLeagues();
  const leagueInfo = leagues.find((l) => l.league === league);
  if (!leagueInfo) {
    notFound();
  }

  const season = seasonParam ?? leagueInfo.seasons[0];
  const [standings, matches, topScorers] = await Promise.all([
    getLeagueStandings(league, season),
    getLeagueMatches(league, season),
    getTopScorers(10, league),
  ]);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{LEAGUE_LABELS[league] ?? league}</h1>
        <SeasonSelect league={league} seasons={leagueInfo.seasons} currentSeason={season} />
      </div>

      <div className="grid gap-8 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <h2 className="mb-4 text-xl font-semibold">Standings</h2>
          <StandingsTable standings={standings} />
        </section>

        <section>
          <h2 className="mb-4 text-xl font-semibold">Top Scorers</h2>
          {topScorers.length === 0 ? (
            <p className="text-sm text-muted-foreground">No data available.</p>
          ) : (
            <ol className="space-y-2">
              {topScorers.map((p, i) => (
                <li key={p.player_id} className="flex items-center justify-between text-sm">
                  <span>
                    {i + 1}. {p.player_name}{" "}
                    <span className="text-muted-foreground">({p.team_name})</span>
                  </span>
                  <span className="font-semibold">{p.goals ?? 0} goals</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Fixtures</h2>
        <MatchList matches={matches} />
      </section>
    </div>
  );
}