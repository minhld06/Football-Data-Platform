import Link from "next/link";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { LeagueStanding } from "@/lib/types";

export default function StandingsTable({ standings }: { standings: LeagueStanding[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>#</TableHead>
          <TableHead>Team</TableHead>
          <TableHead className="text-right">P</TableHead>
          <TableHead className="text-right">W</TableHead>
          <TableHead className="text-right">D</TableHead>
          <TableHead className="text-right">L</TableHead>
          <TableHead className="text-right">GD</TableHead>
          <TableHead className="text-right">Pts</TableHead>
          <TableHead className="text-right">xG</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {standings.map((row) => (
          <TableRow key={row.team_id}>
            <TableCell>{row.position}</TableCell>
            <TableCell>
              <Link href={`/teams/${row.team_id}`} className="hover:underline">
                {row.team_name}
              </Link>
            </TableCell>
            <TableCell className="text-right">{row.played_games}</TableCell>
            <TableCell className="text-right">{row.won}</TableCell>
            <TableCell className="text-right">{row.draw}</TableCell>
            <TableCell className="text-right">{row.lost}</TableCell>
            <TableCell className="text-right">{row.goal_difference}</TableCell>
            <TableCell className="text-right font-semibold">{row.points}</TableCell>
            <TableCell className="text-right text-muted-foreground">
              {row.xg !== null ? row.xg.toFixed(1) : "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}