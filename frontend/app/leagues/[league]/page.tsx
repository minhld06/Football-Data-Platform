import { notFound } from "next/navigation";
import StandingsTable from "@/components/StandingsTable";
import MatchList from "@/components/MatchList";
import SeasonSelect from "@/components/SeasonSelect";
import AsOfDateSelect from "@/components/AsOfDateSelect";
import TopPerformersList from "@/components/TopPerformersList";
import SectionHeading from "@/components/SectionHeading";
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
      <SectionHeading
        as="h1"
        eyebrow="League"
        title={LEAGUE_LABELS[league] ?? league}
        action={
          <div className="flex items-center gap-2">
            <AsOfDateSelect league={league} currentAsOf={asOf} />
            <SeasonSelect league={league} seasons={leagueInfo.seasons} currentSeason={season} />
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
        <section className="lg:col-span-2">
          <SectionHeading
            title="Standings"
            action={asOf && <span className="text-xs text-muted-foreground">as of {asOf}</span>}
          />
          <div className="mt-4">
            <StandingsTable standings={standings} />
          </div>
        </section>

        <div className="space-y-8">
          <TopPerformersList title="Top Scorers" players={topScorers} stat="goals" statLabel="goals" />
          <TopPerformersList title="Top Assists" players={topAssists} stat="assists" statLabel="assists" />
        </div>
      </div>

      <section>
        <SectionHeading title="Fixtures" />
        <div className="mt-4">
          <MatchList matches={matches} />
        </div>
      </section>
    </div>
  );
}