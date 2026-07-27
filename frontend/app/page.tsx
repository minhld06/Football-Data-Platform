import LeagueCard from "@/components/LeagueCard";
import MatchList from "@/components/MatchList";
import { getLeagues, getRecentMatches, getTopScorers } from "@/lib/api";

export default async function HomePage() {
  const [leagues, recentMatches, topScorers] = await Promise.all([
    getLeagues(),
    getRecentMatches(5),
    getTopScorers(5),
  ]);

  return (
    <div className="space-y-10">
      <section>
        <h1 className="mb-4 text-2xl font-bold">Leagues</h1>
        <div className="grid gap-4 sm:grid-cols-2">
          {leagues.map((league) => (
            <LeagueCard key={league.league} league={league} />
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold">Recent Matches</h2>
        <MatchList matches={recentMatches} />
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
  );
}