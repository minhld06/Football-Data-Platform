"use client";

export default function Error({
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-4 py-24 text-center">
      <p className="font-heading text-xs font-semibold tracking-[0.2em] text-destructive uppercase">
        Red card
      </p>
      <h1 className="font-heading text-3xl font-semibold">Something went wrong</h1>
      <p className="text-muted-foreground">
        Could not reach the backend. Please check the server and try again.
      </p>
      <button
        onClick={() => unstable_retry()}
        className="rounded-md border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
      >
        Try again
      </button>
    </div>
  );
}