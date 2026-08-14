import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center gap-4 py-24 text-center">
      <p className="font-heading text-xs font-semibold tracking-[0.2em] text-primary uppercase">
        Offside
      </p>
      <h1 className="font-heading text-5xl font-semibold">404</h1>
      <div className="h-[3px] w-12 bg-primary" />
      <p className="text-muted-foreground">The content you requested could not be found.</p>
      <Link href="/" className="font-medium text-primary hover:underline">
        Back to home
      </Link>
    </div>
  );
}