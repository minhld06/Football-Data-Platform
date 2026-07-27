"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Menu, X } from "lucide-react";
import { Input } from "@/components/ui/input";

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
    <header className="border-b">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:grid sm:grid-cols-3">
        <Link href="/" className="text-lg font-semibold">
          Football Data Platform
        </Link>

        <div className="hidden sm:flex sm:justify-center">
          <NavSearchInput />
        </div>

        <div className="hidden sm:flex sm:items-center sm:justify-end sm:gap-4">
          <Link href="/" className="text-sm hover:underline">
            Home
          </Link>
        </div>

        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          className="flex h-8 w-8 items-center justify-center rounded-md border sm:hidden"
          aria-label="Toggle menu"
          aria-expanded={menuOpen}
        >
          {menuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </nav>

      {menuOpen && (
        <div className="flex flex-col gap-3 border-t px-4 py-3 sm:hidden">
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