import Link from "next/link";
import type { MatchResult } from "@/lib/types";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function MatchList({ matches }: { matches: MatchResult[] }) {
  if (matches.length === 0) {
    return <p className="text-sm text-muted-foreground">No matches available.</p>;
  }

  return (
    <ul className="divide-y">
      {matches.map((m) => (
        <li key={m.source_match_id} className="flex items-center justify-between py-3 text-sm">
          <div className="flex items-center gap-2">
            <Link href={`/teams/${m.home_team_id}`} className="hover:underline">
              {m.home_team_name ?? m.home_team_id}
            </Link>
            <span className="font-medium">
              {m.home_score ?? "-"} : {m.away_score ?? "-"}
            </span>
            <Link href={`/teams/${m.away_team_id}`} className="hover:underline">
              {m.away_team_name ?? m.away_team_id}
            </Link>
          </div>
          <span className="text-muted-foreground">{formatDate(m.utc_date)}</span>
        </li>
      ))}
    </ul>
  );
}