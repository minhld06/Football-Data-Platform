import Link from "next/link";
import type { PlayerPerformance } from "@/lib/types";
import SectionHeading from "@/components/SectionHeading";

export default function TopPerformersList({
  title,
  players,
  stat,
  statLabel,
  showTeamName = true,
}: {
  title: string;
  players: PlayerPerformance[];
  stat: "goals" | "assists";
  statLabel: string;
  showTeamName?: boolean;
}) {
  return (
    <section>
      <div className="mb-4">
        <SectionHeading title={title} />
      </div>
      {players.length === 0 ? (
        <p className="text-sm text-muted-foreground">No data available.</p>
      ) : (
        <ol className="space-y-1">
          {players.map((p, i) => (
            <li
              key={p.player_id}
              className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-primary/5"
            >
              <span className="flex items-center gap-2 truncate">
                <span className="font-heading w-5 shrink-0 text-right text-muted-foreground tabular-nums">
                  {i + 1}
                </span>
                <Link href={`/players/${p.player_id}`} className="truncate font-medium hover:text-primary hover:underline">
                  {p.player_name}
                </Link>
                {showTeamName && (
                  <span className="shrink-0 truncate text-muted-foreground">({p.team_name})</span>
                )}
              </span>
              <span className="font-heading shrink-0 font-semibold text-primary tabular-nums">
                {p[stat] ?? 0} <span className="text-muted-foreground">{statLabel}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
