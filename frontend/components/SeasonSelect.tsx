"use client";

import { useRouter, useSearchParams } from "next/navigation";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function SeasonSelect({
  basePath,
  seasons,
  currentSeason,
}: {
  basePath: string;
  seasons: string[];
  currentSeason: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function handleChange(season: string | null) {
    if (!season) return;
    const params = new URLSearchParams(searchParams.toString());
    params.set("season", season);
    router.push(`${basePath}?${params.toString()}`);
  }

  return (
    <Select value={currentSeason} onValueChange={handleChange}>
      <SelectTrigger className="w-40">
        <SelectValue placeholder="Season" />
      </SelectTrigger>
      <SelectContent>
        {seasons.map((s) => (
          <SelectItem key={s} value={s}>
            {s}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}