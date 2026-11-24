/** Split `text` into [before, match, after] around the half-open range [start, end). */
export function splitAt(text: string, start: number, end: number): [string, string, string] {
  const s = Math.max(0, Math.min(start, text.length));
  const e = Math.max(s, Math.min(end, text.length));
  return [text.slice(0, s), text.slice(s, e), text.slice(e)];
}

/** Steps the founder may open, given the study state. Step 4 is behind the checkpoint. */
export function unlockedSteps(opts: { hasResult: boolean; approved: boolean }): number[] {
  const steps = [1];
  if (opts.hasResult) steps.push(2, 3);
  if (opts.approved) steps.push(4);
  return steps;
}
