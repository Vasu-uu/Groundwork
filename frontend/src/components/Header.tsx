import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Health } from "../api/types";
import { cx } from "./ui";

/** Top bar: brand, model status, and the per-study cost counter. */
export function Header({ costLabel, onHome }: { costLabel?: string; onHome: () => void }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setHealth(h);
        setDown(false);
      })
      .catch(() => setDown(true));
  }, []);

  const ok = health?.llm.ok;
  return (
    <header className="border-b border-stone-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <button type="button" onClick={onHome} className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-lg bg-brand-900 text-brand-100" aria-hidden>
            <svg viewBox="0 0 32 32" className="size-5">
              <path d="M7 22h18M10 17h12M13 12h6" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          </span>
          <span className="text-left">
            <span className="block text-base font-semibold leading-tight text-stone-900">Groundwork</span>
            <span className="block text-xs text-stone-500">Evidence-first customer discovery</span>
          </span>
        </button>
        <div className="flex items-center gap-3 text-xs">
          {costLabel && (
            <span
              className="rounded-md bg-stone-100 px-2 py-1 font-medium tabular-nums text-stone-700"
              title="Runtime models are free (open-weight or free tier): every run costs 0 EUR"
            >
              {costLabel}
            </span>
          )}
          {down ? (
            <span className="rounded-md bg-rose-50 px-2 py-1 font-medium text-rose-800">Server offline</span>
          ) : (
            health && (
              <span
                title={health.llm.detail + (health.llm.hint ? ` — ${health.llm.hint}` : "")}
                className={cx(
                  "flex items-center gap-1.5 rounded-md px-2 py-1 font-medium",
                  ok ? "bg-brand-50 text-brand-800" : "bg-amber-50 text-amber-900",
                )}
              >
                <span className={cx("size-1.5 rounded-full", ok ? "bg-brand-600" : "bg-amber-500")} />
                {health.llm.provider} · {health.llm.model}
                {!ok && " (not ready)"}
              </span>
            )
          )}
        </div>
      </div>
    </header>
  );
}
