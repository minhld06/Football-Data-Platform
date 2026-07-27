import Link from "next/link";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { LeagueSummary } from "@/lib/types";

const LEAGUE_LABELS: Record<string, string> = {
  "premier-league": "Premier League",
  "ligue-1": "Ligue 1",
};

export default function LeagueCard({ league }: { league: LeagueSummary }) {
  const label = LEAGUE_LABELS[league.league] ?? league.league;
  return (
    <Link href={`/leagues/${league.league}`}>
      <Card className="transition hover:border-primary">
        <CardHeader>
          <CardTitle>{label}</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {league.seasons.length} Leagues available · Latest: {league.seasons[0]}
        </CardContent>
      </Card>
    </Link>
  );
}