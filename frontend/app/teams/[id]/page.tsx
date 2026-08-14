import TeamFormBadges from "@/components/TeamFormBadges";
import MatchList from "@/components/MatchList";
import SquadTable from "@/components/SquadTable";
import TopPerformersList from "@/components/TopPerformersList";
import SectionHeading from "@/components/SectionHeading";
import {
  getTeam,
  getTeamForm,
  getTeamMatches,
  getTeamSquad,
  getTopScorers,
  getTopAssists,
} from "@/lib/api";

export default async function TeamPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const teamId = Number(id);

  const [team, matches, form, squad, topScorers, topAssists] = await Promise.all([
    getTeam(teamId),
    getTeamMatches(teamId),
    getTeamForm(teamId),
    getTeamSquad(teamId),
    getTopScorers({ teamId, limit: 5 }),
    getTopAssists({ teamId, limit: 5 }),
  ]);

  return (
    <div className="space-y-8">
      <SectionHeading
        as="h1"
        eyebrow="Team"
        title={team.team_name}
        subtitle={`${team.team_tla ?? team.team_short_name ?? ""} · ${team.league}`}
      />

      {form && (
        <section>
          <SectionHeading title="Form (last 5 matches)" />
          <div className="mt-3">
            <TeamFormBadges form={form.form} />
          </div>
        </section>
      )}

      <section>
        <SectionHeading title="Squad" />
        <div className="mt-4">
          <SquadTable players={squad} />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        <TopPerformersList title="Top Scorers" players={topScorers} stat="goals" statLabel="goals" showTeamName={false} />
        <TopPerformersList title="Top Assists" players={topAssists} stat="assists" statLabel="assists" showTeamName={false} />
      </div>

      <section>
        <SectionHeading title="Matches" />
        <div className="mt-4">
          <MatchList matches={matches} />
        </div>
      </section>
    </div>
  );
}
