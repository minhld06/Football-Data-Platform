import Link from "next/link";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { PlayerProfile } from "@/lib/types";

const POSITION_GROUPS = ["Goalkeeper", "Defence", "Midfield", "Offence"];

export default function SquadTable({ players }: { players: PlayerProfile[] }) {
  if (players.length === 0) {
    return <p className="text-sm text-muted-foreground">No squad data available.</p>;
  }

  const groups = POSITION_GROUPS.map((group) => ({
    group,
    players: players.filter((p) => p.position === group),
  }));

  const ungrouped = players.filter((p) => !POSITION_GROUPS.includes(p.position ?? ""));
  if (ungrouped.length > 0) {
    groups.push({ group: "No Position Data", players: ungrouped });
  }

  return (
    <div className="space-y-6">
      {groups
        .filter((g) => g.players.length > 0)
        .map(({ group, players: groupPlayers }) => (
          <div key={group}>
            <h3 className="mb-2 text-sm font-semibold text-muted-foreground">{group}</h3>
            {group === "No Position Data" && (
              <p className="mb-2 text-xs text-muted-foreground">
                Fringe squad players with too few appearances for our data source to record a primary position.
              </p>
            )}
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12">#</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Nationality</TableHead>
                  <TableHead className="text-right">Age</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {groupPlayers.map((p) => (
                  <TableRow key={p.player_id}>
                    <TableCell>{p.shirt_number ?? "—"}</TableCell>
                    <TableCell>
                      <Link href={`/players/${p.player_id}`} className="hover:underline">
                        {p.player_name}
                      </Link>
                    </TableCell>
                    <TableCell>{p.nationality ?? "—"}</TableCell>
                    <TableCell className="text-right">{p.age ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ))}
    </div>
  );
}
