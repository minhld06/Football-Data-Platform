import { Badge } from "@/components/ui/badge";

const VARIANT: Record<string, string> = {
  W: "bg-green-600 hover:bg-green-600",
  D: "bg-gray-400 hover:bg-gray-400",
  L: "bg-red-600 hover:bg-red-600",
};

export default function TeamFormBadges({ form }: { form: string }) {
  return (
    <div className="flex gap-1">
      {form.split("").map((letter, i) => (
        <Badge key={i} className={`${VARIANT[letter] ?? ""} text-white`}>
          {letter}
        </Badge>
      ))}
    </div>
  );
}