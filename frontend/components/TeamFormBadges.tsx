import { Badge } from "@/components/ui/badge";

const VARIANT: Record<string, string> = {
  W: "bg-primary text-primary-foreground hover:bg-primary",
  D: "bg-muted text-muted-foreground hover:bg-muted",
  L: "bg-destructive text-white hover:bg-destructive",
};

export default function TeamFormBadges({ form }: { form: string }) {
  const letters = form.split("").filter((ch) => ch in VARIANT);
  return (
    <div className="flex gap-1">
      {letters.map((letter, i) => (
        <Badge key={i} className={`${VARIANT[letter] ?? ""} font-heading`}>
          {letter}
        </Badge>
      ))}
    </div>
  );
}