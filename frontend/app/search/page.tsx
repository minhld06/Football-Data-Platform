import Link from "next/link";
import SearchBox from "@/components/SearchBox";
import SectionHeading from "@/components/SectionHeading";
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
      <SectionHeading as="h1" eyebrow="Find" title="Search" />
      <SearchBox initialQuery={q ?? ""} />

      {q && (
        <div>
          {results.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No results found for &quot;{q}&quot;.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {results.map((r) => (
                <li key={`${r.type}-${r.id}`} className="py-1">
                  <Link
                    href={resultHref(r)}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-2 transition-colors hover:bg-primary/5"
                  >
                    <span className="font-medium hover:text-primary hover:underline">{r.name}</span>
                    <span className="font-heading text-xs tracking-wide text-primary uppercase">
                      {r.type === "team" ? "Team" : "Player"}
                      {r.subtitle ? ` · ${r.subtitle}` : ""}
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