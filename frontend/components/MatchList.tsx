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
    <ul className="divide-y divide-border">
      {matches.map((m) => (
        <li
          key={m.source_match_id}
          className="flex items-center justify-between gap-4 py-3 text-sm transition-colors hover:bg-primary/5"
        >
          <div className="flex flex-1 items-center justify-end gap-2 text-right">
            <Link href={`/teams/${m.home_team_id}`} className="font-medium hover:text-primary hover:underline">
              {m.home_team_name ?? m.home_team_id}
            </Link>
          </div>
          <span className="font-heading shrink-0 rounded-md bg-muted px-2.5 py-1 text-sm font-semibold tabular-nums">
            {m.home_score ?? "-"} : {m.away_score ?? "-"}
          </span>
          <div className="flex flex-1 items-center gap-2">
            <Link href={`/teams/${m.away_team_id}`} className="font-medium hover:text-primary hover:underline">
              {m.away_team_name ?? m.away_team_id}
            </Link>
          </div>
          <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">
            {formatDate(m.utc_date)}
          </span>
        </li>
      ))}
    </ul>
  );
}