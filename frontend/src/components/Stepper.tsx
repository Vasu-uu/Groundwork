import { cx } from "./ui";

export const STEPS = [
  { n: 1, label: "Interviews & hypotheses" },
  { n: 2, label: "Evidence" },
  { n: 3, label: "Your review" },
  { n: 4, label: "Next interview" },
] as const;

/** Four-step progress bar. Locked steps are visible but not clickable. */
export function Stepper({
  current,
  unlocked,
  done,
  onSelect,
}: {
  current: number;
  unlocked: number[];
  done: number[];
  onSelect: (step: number) => void;
}) {
  return (
    <nav aria-label="Progress" className="mb-8">
      <ol className="grid grid-cols-4 gap-2">
        {STEPS.map((s) => {
          const open = unlocked.includes(s.n);
          const active = s.n === current;
          const complete = done.includes(s.n);
          return (
            <li key={s.n}>
              <button
                type="button"
                disabled={!open}
                onClick={() => onSelect(s.n)}
                aria-current={active ? "step" : undefined}
                className="group w-full text-left disabled:cursor-not-allowed"
              >
                <span
                  className={cx(
                    "block h-1.5 rounded-full transition",
                    active ? "bg-brand-700" : complete ? "bg-brand-600/60" : "bg-stone-200",
                  )}
                />
                <span
                  className={cx(
                    "mt-2 flex items-center gap-1.5 text-xs font-medium sm:text-sm",
                    active ? "text-brand-800" : open ? "text-stone-700 group-hover:text-stone-900" : "text-stone-400",
                  )}
                >
                  <span className="tabular-nums">{complete && !active ? "✓" : s.n}</span>
                  <span className="truncate">{s.label}</span>
                  {s.n === 3 && <span className="hidden text-[10px] uppercase tracking-wide text-amber-700 md:inline">checkpoint</span>}
                  {!open && <span aria-label="locked">🔒</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
