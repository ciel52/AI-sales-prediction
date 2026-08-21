"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "ome-easy-read";

export function EasyReadToggle() {
  const [on, setOn] = useState(false);

  useEffect(() => {
    setOn(document.documentElement.classList.contains("easy-read"));
  }, []);

  function toggle() {
    const next = !document.documentElement.classList.contains("easy-read");
    document.documentElement.classList.toggle("easy-read", next);
    try {
      localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
    } catch {
      /* ignore */
    }
    setOn(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-pressed={on}
      title="色と字の太さで、重要な数字をはっきり見せます"
      className={
        on
          ? "whitespace-nowrap rounded-full bg-[var(--ink)] px-2.5 py-1.5 text-xs font-medium text-white sm:px-4 sm:text-sm"
          : "whitespace-nowrap rounded-full border border-[var(--line)] bg-white px-2.5 py-1.5 text-xs text-[var(--ink)] hover:bg-[var(--wash)] sm:px-4 sm:text-sm"
      }
    >
      <span className="sm:hidden">はっきり</span>
      <span className="hidden sm:inline">見やすい表示</span>
    </button>
  );
}
