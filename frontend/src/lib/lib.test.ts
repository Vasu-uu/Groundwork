import { describe as log } from "../components/DecisionLog";
import { parseHash } from "../hooks/useHashRoute";
import { splitAt, unlockedSteps } from "./highlight";

describe("splitAt", () => {
  it("splits text around the highlighted range", () => {
    expect(splitAt("abcdef", 2, 4)).toEqual(["ab", "cd", "ef"]);
  });
  it("clamps out-of-range offsets", () => {
    expect(splitAt("abc", -5, 99)).toEqual(["", "abc", ""]);
  });
});

describe("unlockedSteps", () => {
  it("only allows inputs before any analysis", () => {
    expect(unlockedSteps({ hasResult: false, approved: false })).toEqual([1]);
  });
  it("opens evidence and review once analysed, but not the next step", () => {
    expect(unlockedSteps({ hasResult: true, approved: false })).toEqual([1, 2, 3]);
  });
  it("opens step 4 only after approval", () => {
    expect(unlockedSteps({ hasResult: true, approved: true })).toEqual([1, 2, 3, 4]);
  });
});

describe("parseHash", () => {
  it("routes home by default", () => {
    expect(parseHash("")).toEqual({ page: "home" });
    expect(parseHash("#/")).toEqual({ page: "home" });
  });
  it("parses study routes and clamps the step", () => {
    expect(parseHash("#/study/abc-1/3")).toEqual({ page: "study", id: "abc-1", step: 3 });
    expect(parseHash("#/study/abc")).toEqual({ page: "study", id: "abc", step: 1 });
    expect(parseHash("#/study/abc/9")).toEqual({ page: "study", id: "abc", step: 4 });
  });
});

describe("decision log descriptions", () => {
  const base = { id: 1, at: "2026-11-24T10:00:00Z", actor: "founder" as const, hypothesis_id: "H1" };
  it("summarises a review edit with the founder's reasoning", () => {
    const text = log({
      ...base,
      action: "review_saved",
      details: { ai_suggestion: "VALIDATED", after: { decision: "change", final_verdict: "MIXED", reasoning: "Only power users" } },
    });
    expect(text).toBe("change (AI said VALIDATED, final MIXED): “Only power users”");
  });
  it("shows rejected hypotheses as re-test", () => {
    const text = log({ ...base, action: "approved", details: { final_verdicts: { H1: "VALIDATED", H2: null } } });
    expect(text).toBe("H1 VALIDATED · H2 re-test");
  });
});
