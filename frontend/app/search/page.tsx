import Link from "next/link";
import SearchBox from "@/components/SearchBox";
import { search } from "@/lib/api";
import type { SearchResult } from "@/lib/types";

function resultHref(result: SearchResult): string {
  return result.type === "team" ? `/teams/${result.id}` : `/players/${result.id}`;
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const results = q && q.trim().length >= 2 ? await search(q.trim()) : [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Search</h1>
      <SearchBox initialQuery={q ?? ""} />

      {q && (
        <div>
          {results.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No results found for &quot;{q}&quot;.
            </p>
          ) : (
            <ul className="divide-y">
              {results.map((r) => (
                <li key={`${r.type}-${r.id}`} className="py-3">
                  <Link href={resultHref(r)} className="hover:underline">
                    <span className="font-medium">{r.name}</span>{" "}
                    <span className="text-sm text-muted-foreground">
                      ({r.type === "team" ? "Team" : "Player"}
                      {r.subtitle ? ` · ${r.subtitle}` : ""})
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}