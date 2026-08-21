"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { EasyReadToggle } from "@/components/EasyReadToggle";

const NAV = [
  { href: "/", label: "予測デスク" },
  { href: "/algorithm", label: "予測のしくみ" },
];

export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="border-b border-[var(--line)] bg-[var(--panel)]/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-2 px-3 py-2.5 sm:gap-4 sm:px-6 sm:py-3 lg:px-8">
        <Link href="/" className="min-w-0 shrink">
          <p className="text-[9px] font-semibold tracking-[0.12em] text-[var(--accent)] sm:text-[10px] sm:tracking-[0.18em]">
            OME DX / CLEANSMARED
          </p>
          <p className="m-plus-rounded-1c-regular truncate text-sm text-[var(--ink)]">
            来店・売上予測
          </p>
        </Link>
        <div className="flex shrink-0 items-center gap-1 sm:gap-2">
          <nav className="flex shrink-0 gap-1">
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
                      ? "whitespace-nowrap rounded-full bg-[var(--accent)] px-2.5 py-1.5 text-xs font-medium text-white sm:px-4 sm:text-sm"
                      : "whitespace-nowrap rounded-full px-2.5 py-1.5 text-xs text-[var(--ink)] hover:bg-white sm:px-4 sm:text-sm"
                  }
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <EasyReadToggle />
        </div>
      </div>
    </header>
  );
}
