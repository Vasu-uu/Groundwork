import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { api, ApiError } from "../api/client";
import type { InterviewScript } from "../api/types";
import { study } from "../test/fixtures";
import { NextStep } from "./NextStep";

vi.mock("../api/client", async (orig) => {
  const mod = await orig<typeof import("../api/client")>();
  return {
    ...mod,
    api: {
      ...mod.api,
      decisions: vi.fn().mockResolvedValue([]),
      script: vi.fn(),
      generateScript: vi.fn(),
      saveScript: vi.fn(),
    },
  };
});

const SCRIPT: InterviewScript = {
  generated_at: "2026-11-24T10:00:00Z",
  edited_at: null,
  prompt_id: "draft_interview_script.v1",
  model: "ollama:qwen2.5:7b",
  targets: [{ id: "H2", kind: "hypothesis", text: "Hypothesis H2", reason: "Evidence is split." }],
  questions: [
    {
      id: "Q1",
      section: "hypothesis",
      target: "H2",
      question: "Would you pay for reminders?",
      purpose: "Test H2",
      bias_check: "Asks directly.",
      follow_ups: ["Why?"],
      lint: ["Hypothetical: people are poor predictors of their own behaviour."],
      needs_edit: false,
      edited: false,
    },
  ],
  warnings: [],
};

const approved = () => study({ status: "approved", approved_at: "2026-11-24T10:00:00Z" });

describe("NextStep", () => {
  it("drafts a script on request and shows wording problems", async () => {
    vi.mocked(api.script).mockRejectedValue(new ApiError(404, "no_script", "No interview script yet."));
    vi.mocked(api.generateScript).mockResolvedValue(SCRIPT);
    const refresh = vi.fn().mockResolvedValue(null);
    render(<NextStep study={approved()} refresh={refresh} />);

    fireEvent.click(await screen.findByRole("button", { name: /draft the next interview script/i }));
    expect(await screen.findByText("Would you pay for reminders?")).toBeInTheDocument();
    expect(screen.getByLabelText("Wording problems")).toHaveTextContent("Hypothetical");
    expect(screen.getByText("Asks directly.")).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
  });

  it("explains an unreachable model", async () => {
    vi.mocked(api.script).mockRejectedValue(new ApiError(404, "no_script", ""));
    vi.mocked(api.generateScript).mockRejectedValue(new ApiError(503, "provider_unavailable", "Cannot reach Ollama."));
    render(<NextStep study={approved()} refresh={vi.fn().mockResolvedValue(null)} />);
    fireEvent.click(await screen.findByRole("button", { name: /draft the next interview script/i }));
    expect(await screen.findByText("The language model could not be reached")).toBeInTheDocument();
  });

  it("saves edited questions and offers both export formats", async () => {
    vi.mocked(api.script).mockResolvedValue(SCRIPT);
    vi.mocked(api.saveScript).mockResolvedValue({ ...SCRIPT, edited_at: "2026-11-24T11:00:00Z" });
    render(<NextStep study={approved()} refresh={vi.fn().mockResolvedValue(null)} />);

    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByDisplayValue("Would you pay for reminders?"), {
      target: { value: "How do you handle overdue invoices today?" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save script/i }));
    await waitFor(() =>
      expect(api.saveScript).toHaveBeenCalledWith("s1", [
        expect.objectContaining({ id: "Q1", question: "How do you handle overdue invoices today?", follow_ups: ["Why?"] }),
      ]),
    );
    expect(screen.getByRole("link", { name: "Markdown" })).toHaveAttribute("href", "/api/studies/s1/report.md");
    expect(screen.getByRole("link", { name: "PDF" })).toHaveAttribute("href", "/api/studies/s1/report.pdf");
  });
});
