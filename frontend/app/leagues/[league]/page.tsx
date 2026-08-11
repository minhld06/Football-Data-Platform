import { notFound } from "next/navigation";
import StandingsTable from "@/components/StandingsTable";
import MatchList from "@/components/MatchList";
import SeasonSelect from "@/components/SeasonSelect";
import AsOfDateSelect from "@/components/AsOfDateSelect";
import TopPerformersList from "@/components/TopPerformersList";
import { getLeagues, getLeagueStandings, getLeagueMatches, getTopScorers, getTopAssists } from "@/lib/api";

const LEAGUE_LABELS: Record<string, string> = {
  "premier-league": "Premier League",
  "ligue-1": "Ligue 1",
};

export default async function LeaguePage({
  params,
  searchParams,
}: {
  params: Promise<{ league: string }>;
  searchParams: Promise<{ season?: string; as_of?: string }>;
}) {
  const { league } = await params;
  const { season: seasonParam, as_of: asOf } = await searchParams;

  const leagues = await getLeagues();
  const leagueInfo = leagues.find((l) => l.league === league);
  if (!leagueInfo) {
    notFound();
  }

  const season = seasonParam ?? leagueInfo.seasons[0];
  const [standings, matches, topScorers, topAssists] = await Promise.all([
    getLeagueStandings(league, season, asOf),
    getLeagueMatches(league, season),
    getTopScorers({ limit: 10, league }),
    getTopAssists({ limit: 10, league }),
  ]);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">{LEAGUE_LABELS[league] ?? league}</h1>
        <div className="flex items-center gap-2">
          <AsOfDateSelect league={league} currentAsOf={asOf} />
          <SeasonSelect league={league} seasons={leagueInfo.seasons} currentSeason={season} />
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-xl font-semibold">Standings</h2>
            {asOf && <span className="text-sm text-muted-foreground">as of {asOf}</span>}
          </div>
          <StandingsTable standings={standings} />
        </section>

        <div className="space-y-8">
          <TopPerformersList title="Top Scorers" players={topScorers} stat="goals" statLabel="goals" />
          <TopPerformersList title="Top Assists" players={topAssists} stat="assists" statLabel="assists" />
        </div>
      </div>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Fixtures</h2>
        <MatchList matches={matches} />
      </section>
    </div>
  );
}