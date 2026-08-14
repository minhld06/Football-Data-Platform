"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Menu, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import ThemeToggle from "@/components/ThemeToggle";

function NavSearchInput() {
  const [value, setValue] = useState("");
  const router = useRouter();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (value.trim().length < 2) return;
    router.push(`/search?q=${encodeURIComponent(value.trim())}`);
  }

  return (
    <form onSubmit={handleSubmit}>
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Search..."
        className="h-8 w-40 sm:w-56"
      />
    </form>
  );
}

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-border/80 bg-background/85 backdrop-blur-sm">
      <div className="h-[3px] w-full bg-primary" />
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:grid sm:grid-cols-3">
        <Link href="/" className="font-heading text-lg font-semibold tracking-wide uppercase">
          Football<span className="text-primary">Data</span>
        </Link>

        <div className="hidden sm:flex sm:justify-center">
          <NavSearchInput />
        </div>

        <div className="hidden sm:flex sm:items-center sm:justify-end sm:gap-2">
          <Link
            href="/"
            className="px-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Home
          </Link>
          <ThemeToggle />
        </div>

        <div className="flex items-center gap-1 sm:hidden">
          <ThemeToggle />
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            className="flex h-8 w-8 items-center justify-center rounded-md border border-border"
            aria-label="Toggle menu"
            aria-expanded={menuOpen}
          >
            {menuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </nav>

      {menuOpen && (
        <div className="flex flex-col gap-3 border-t border-border px-4 py-3 sm:hidden">
          <Link
            href="/"
            className="text-sm hover:underline"
            onClick={() => setMenuOpen(false)}
          >
            Home
          </Link>
          <NavSearchInput />
        </div>
      )}
    </header>
  );
}