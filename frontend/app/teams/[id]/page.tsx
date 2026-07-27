import TeamFormBadges from "@/components/TeamFormBadges";
import MatchList from "@/components/MatchList";
import { getTeam, getTeamForm, getTeamMatches } from "@/lib/api";

export default async function TeamPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const teamId = Number(id);

  const [team, matches, form] = await Promise.all([
    getTeam(teamId),
    getTeamMatches(teamId),
    getTeamForm(teamId),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">{team.team_name}</h1>
        <p className="text-sm text-muted-foreground">
          {team.team_tla ?? team.team_short_name ?? ""} · {team.league}
        </p>
      </div>

      {form && (
        <section>
          <h2 className="mb-2 text-xl font-semibold">Form (last 5 matches)</h2>
          <TeamFormBadges form={form.form} />
        </section>
      )}

      <section>
        <h2 className="mb-4 text-xl font-semibold">Matches</h2>
        <MatchList matches={matches} />
      </section>
    </div>
  );
}