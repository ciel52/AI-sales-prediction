"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "予測デスク" },
  { href: "/algorithm", label: "予測のしくみ" },
];

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="border-b border-[var(--line)] bg-[var(--panel)]/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
        <Link href="/" className="min-w-0">
          <p className="text-[10px] font-semibold tracking-[0.18em] text-[var(--accent)]">
            OME DX / CLEANSMARED
          </p>
          <p className="m-plus-rounded-1c-regular truncate text-sm text-[var(--ink)]">
            来店・売上予測
          </p>
        </Link>
        <nav className="flex gap-1">
          {NAV.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  active
                    ? "rounded-full bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white sm:px-4"
                    : "rounded-full px-3 py-1.5 text-sm text-[var(--ink)] hover:bg-white sm:px-4"
                }
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
