import LeagueCard from "@/components/LeagueCard";
import MatchList from "@/components/MatchList";
import SectionHeading from "@/components/SectionHeading";
import { getLeagues, getRecentMatches } from "@/lib/api";

export default async function HomePage() {
  const [leagues, recentMatches] = await Promise.all([
    getLeagues(),
    getRecentMatches(5),
  ]);

  return (
    <div className="space-y-10">
      <section>
        <SectionHeading as="h1" eyebrow="Overview" title="Leagues" />
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {leagues.map((league) => (
            <LeagueCard key={league.league} league={league} />
          ))}
        </div>
      </section>

      <section>
        <SectionHeading title="Recent Matches" />
        <div className="mt-4">
          <MatchList matches={recentMatches} />
        </div>
      </section>
    </div>
  );
}