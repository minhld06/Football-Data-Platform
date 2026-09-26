import TeamFormBadges from "@/components/TeamFormBadges";
import MatchList from "@/components/MatchList";
import SquadTable from "@/components/SquadTable";
import TopPerformersList from "@/components/TopPerformersList";
import SectionHeading from "@/components/SectionHeading";
import SeasonSelect from "@/components/SeasonSelect";
import {
  getLeagues,
  getTeam,
  getTeamForm,
  getTeamMatches,
  getTeamSquad,
  getTopScorers,
  getTopAssists,
} from "@/lib/api";

export default async function TeamPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ season?: string }>;
}) {
  const { id } = await params;
  const { season: seasonParam } = await searchParams;
  const teamId = Number(id);

  const [team, leagues] = await Promise.all([getTeam(teamId), getLeagues()]);
  const seasons = leagues.find((l) => l.league === team.league)?.seasons ?? [];
  const season = seasonParam ?? seasons[0];

  const [matches, form, squad, topScorers, topAssists] = await Promise.all([
    getTeamMatches(teamId, season),
    getTeamForm(teamId),
    getTeamSquad(teamId, season),
    getTopScorers({ teamId, season, limit: 5 }),
    getTopAssists({ teamId, season, limit: 5 }),
  ]);

  return (
    <div className="space-y-8">
      <SectionHeading
        as="h1"
        eyebrow="Team"
        title={team.team_name}
        subtitle={`${team.team_tla ?? team.team_short_name ?? ""} · ${team.league}`}
        action={
          seasons.length > 0 && (
            <SeasonSelect basePath={`/teams/${teamId}`} seasons={seasons} currentSeason={season} />
          )
        }
      />

      {/* The form endpoint only knows the latest season, so hide it for past seasons */}
      {form && season === seasons[0] && (
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
