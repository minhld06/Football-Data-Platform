import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export default function SectionHeading({
  as: Tag = "h2",
  eyebrow,
  title,
  subtitle,
  action,
}: {
  as?: "h1" | "h2";
  eyebrow?: string;
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  const isH1 = Tag === "h1";
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && (
          <p className="font-heading text-xs font-semibold tracking-[0.2em] text-primary uppercase">
            {eyebrow}
          </p>
        )}
        <Tag
          className={cn(
            "font-heading font-semibold tracking-wide",
            isH1 ? "text-3xl uppercase" : "text-xl"
          )}
        >
          {title}
        </Tag>
        <div className={cn("mt-2 bg-primary", isH1 ? "h-[3px] w-12" : "h-[2px] w-8")} />
        {subtitle && <div className="mt-3 text-sm text-muted-foreground">{subtitle}</div>}
      </div>
      {action && <div className="pb-1">{action}</div>}
    </div>
  );
}
