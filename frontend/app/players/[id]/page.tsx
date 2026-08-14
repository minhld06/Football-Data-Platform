import { getPlayer, getPlayerPerformance } from "@/lib/api";
import SectionHeading from "@/components/SectionHeading";

function stat(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value}`;
}

function statDecimal(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(2);
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border-t-2 border-t-primary bg-card p-4 ring-1 ring-foreground/10">
      <p className="text-xs tracking-wide text-muted-foreground uppercase">{label}</p>
      <p className="font-heading text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

export default async function PlayerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const playerId = Number(id);

  const [player, performance] = await Promise.all([
    getPlayer(playerId),
    getPlayerPerformance(playerId),
  ]);

  return (
    <div className="space-y-8">
      <SectionHeading
        as="h1"
        eyebrow="Player"
        title={player.player_name}
        subtitle={
          <>
            {player.position ?? "—"} · {player.team_name ?? "—"}
            {player.is_on_loan && ` (on loan from ${player.parent_team_name ?? "—"})`} ·{" "}
            {player.league}
          </>
        }
      />

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label="Goals" value={stat(performance.goals)} />
        <Stat label="Assists" value={stat(performance.assists)} />
        <Stat label="Appearances" value={stat(performance.apps)} />
        <Stat label="Minutes" value={stat(performance.minutes)} />
        <Stat label="xG" value={statDecimal(performance.xg)} />
        <Stat label="xA" value={statDecimal(performance.xa)} />
        <Stat label="xG/90" value={statDecimal(performance.xg90)} />
        <Stat label="xA/90" value={statDecimal(performance.xa90)} />
      </section>
    </div>
  );
}