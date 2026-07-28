import LeagueCard from "@/components/LeagueCard";
import MatchList from "@/components/MatchList";
import { getLeagues, getRecentMatches } from "@/lib/api";

export default async function HomePage() {
  const [leagues, recentMatches] = await Promise.all([
    getLeagues(),
    getRecentMatches(5),
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
    </div>
  );
}