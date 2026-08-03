import Link from "next/link";
import type { PlayerPerformance } from "@/lib/types";

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
      <h2 className="mb-4 text-xl font-semibold">{title}</h2>
      {players.length === 0 ? (
        <p className="text-sm text-muted-foreground">No data available.</p>
      ) : (
        <ol className="space-y-2">
          {players.map((p, i) => (
            <li key={p.player_id} className="flex items-center justify-between text-sm">
              <span>
                {i + 1}.{" "}
                <Link href={`/players/${p.player_id}`} className="hover:underline">
                  {p.player_name}
                </Link>
                {showTeamName && (
                  <>
                    {" "}
                    <span className="text-muted-foreground">({p.team_name})</span>
                  </>
                )}
              </span>
              <span className="font-semibold">
                {p[stat] ?? 0} {statLabel}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
