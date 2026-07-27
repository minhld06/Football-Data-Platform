import Link from "next/link";

export default function Navbar() {
  return (
    <header className="border-b">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <Link href="/" className="text-lg font-semibold">
          Football Data Platform
        </Link>
        <div className="flex gap-4 text-sm">
          <Link href="/" className="hover:underline">
            Home
          </Link>
          <Link href="/search" className="hover:underline">
            Search
          </Link>
        </div>
      </nav>
    </header>
  );
}