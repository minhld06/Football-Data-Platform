import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center gap-4 py-20 text-center">
      <h1 className="text-3xl font-bold">404</h1>
      <p className="text-muted-foreground">The content you requested could not be found.</p>
      <Link href="/" className="text-primary hover:underline">
        Back to home
      </Link>
    </div>
  );
}