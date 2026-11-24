import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { api } from "../api/client";
import type { Review } from "../api/types";
import { HypothesisCard } from "../components/HypothesisCard";
import { study, verdict } from "../test/fixtures";
import { ReviewStep } from "./ReviewStep";

vi.mock("../api/client", async (orig) => {
  const mod = await orig<typeof import("../api/client")>();
  return {
    ...mod,
    api: { ...mod.api, decisionLog: vi.fn().mockResolvedValue([]), review: vi.fn(), approve: vi.fn() },
  };
});

function review(id: string): Review {
  return {
    hypothesis_id: id,
    decision: "approve",
    ai_verdict: "VALIDATED",
    final_verdict: "VALIDATED",
    reasoning: "",
    removed_evidence: [],
    note: "",
    reviewed_at: "2026-11-24T10:10:00Z",
    recomputed_ai_verdict: "VALIDATED",
  };
}

describe("ReviewStep checkpoint", () => {
  it("keeps 'Approve and continue' disabled until every verdict is reviewed", () => {
    render(<ReviewStep study={study()} setStudy={() => {}} goStep={() => {}} />);
    expect(screen.getByRole("button", { name: /approve and continue/i })).toBeDisabled();
    expect(screen.getByText("0 of 2 reviewed")).toBeInTheDocument();
    expect(screen.getByText(/review 2 more verdicts \(H1, H2\)/i)).toBeInTheDocument();
  });

  it("enables approval once all are reviewed", () => {
    const s = study({
      reviews: { H1: review("H1"), H2: review("H2") },
      checkpoint: { total: 2, reviewed: 2, missing: [], approved: false, can_approve: true, needs_small_sample_ack: false },
    });
    render(<ReviewStep study={s} setStudy={() => {}} goStep={() => {}} />);
    expect(screen.getByRole("button", { name: /approve and continue/i })).toBeEnabled();
  });

  it("requires the small-sample acknowledgement when there are fewer than 5 interviews", () => {
    const s = study({
      reviews: { H1: review("H1"), H2: review("H2") },
      checkpoint: { total: 2, reviewed: 2, missing: [], approved: false, can_approve: true, needs_small_sample_ack: true },
    });
    render(<ReviewStep study={s} setStudy={() => {}} goStep={() => {}} />);
    const approve = screen.getByRole("button", { name: /approve and continue/i });
    expect(approve).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /provisional/i }));
    expect(approve).toBeEnabled();
  });

  it("requires a reason before changing a verdict", async () => {
    const setStudy = vi.fn();
    vi.mocked(api.review).mockResolvedValue(study());
    render(<ReviewStep study={study()} setStudy={setStudy} goStep={() => {}} />);
    fireEvent.click(screen.getAllByRole("radio", { name: /change/i })[0]!);
    const save = screen.getAllByRole("button", { name: /save decision/i })[0]!;
    expect(save).toBeDisabled();
    fireEvent.change(screen.getAllByRole("textbox", { name: /reasoning/i })[0]!, {
      target: { value: "Only agencies said this" },
    });
    expect(save).toBeDisabled(); // no verdict chosen yet
    fireEvent.change(screen.getAllByRole("combobox", { name: /your verdict/i })[0]!, {
      target: { value: "INVALIDATED" },
    });
    expect(save).toBeEnabled();
    fireEvent.click(save);
    await waitFor(() =>
      expect(api.review).toHaveBeenCalledWith("s1", "H1", expect.objectContaining({ decision: "change", verdict: "INVALIDATED" })),
    );
    expect(setStudy).toHaveBeenCalled();
  });
});

describe("HypothesisCard", () => {
  it("labels the verdict as an AI suggestion and shows both sides", () => {
    render(<HypothesisCard v={verdict("H1")} devilsAdvocate={false} />);
    expect(screen.getByText("AI suggestion")).toBeInTheDocument();
    expect(screen.getByText("Supporting (2)")).toBeInTheDocument();
    expect(screen.getByText("Contradicting (1)")).toBeInTheDocument();
    expect(screen.queryByText(/devil's advocate/i)).not.toBeInTheDocument();
  });

  it("surfaces counter-evidence in devil's advocate mode", () => {
    render(<HypothesisCard v={verdict("H1")} devilsAdvocate />);
    expect(screen.getByText(/strongest evidence against/i)).toBeInTheDocument();
    expect(screen.getAllByText("Clients pay me on time.")).toHaveLength(2);
  });
});
