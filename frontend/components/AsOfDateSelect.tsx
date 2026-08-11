"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function AsOfDateSelect({
  league,
  currentAsOf,
}: {
  league: string;
  currentAsOf?: string;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  function handleChange(value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set("as_of", value);
    } else {
      params.delete("as_of");
    }
    router.push(`/leagues/${league}?${params.toString()}`);
  }

  return (
    <div className="flex items-center gap-2">
      <Input
        type="date"
        value={currentAsOf ?? ""}
        onChange={(e) => handleChange(e.target.value)}
        className="w-40"
        aria-label="Standings as of date"
      />
      {currentAsOf && (
        <Button variant="ghost" size="sm" onClick={() => handleChange("")}>
          Clear
        </Button>
      )}
    </div>
  );
}
