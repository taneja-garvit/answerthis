import { screen, waitFor, within } from "@testing-library/react";

import { liveClaims } from "../../test/mockBackend";
import { setup } from "../../test/render";

const [claim1, claim2, claim3] = liveClaims as [typeof liveClaims[0], typeof liveClaims[0], typeof liveClaims[0]];
const open = (claimId = "") => setup(`/review/proj-1${claimId ? `?claim=${claimId}` : ""}`, { seeded: true });
const sidebar = () => screen.getByRole("navigation", { name: "Claims" });
const review = () => screen.getByRole("article");
const decision = (name: string) => screen.getByRole("radio", { name });

describe("Review workspace — navigation", () => {
  it("lists claims with AI verdict and review state, and opens the first unreviewed claim", async () => {
    const { router } = open();
    await screen.findByRole("heading", { name: "Claim 1 of 3" });
    const items = within(sidebar()).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(within(items[0]!).getByText("Supported")).toBeInTheDocument();
    expect(within(items[1]!).getByText("Partial")).toBeInTheDocument();
    expect(within(items[2]!).getByText("Unsupported")).toBeInTheDocument();
    for (const item of items) expect(within(item).getByText("Needs review")).toBeInTheDocument();
    expect(within(sidebar()).getByText("0 of 3 reviewed")).toBeInTheDocument();
    expect(within(items[0]!).getByRole("button")).toHaveAttribute("aria-current", "true");
    await waitFor(() => expect(router.state.location.search).toBe(`?claim=${claim1.id}`));
  });

  it("selecting a claim changes the workspace and the URL; deep links open that claim", async () => {
    const { user, router } = open();
    await screen.findByRole("heading", { name: "Claim 1 of 3" });
    await user.click(within(sidebar()).getByText(claim2.claim_text));
    expect(screen.getByRole("heading", { name: "Claim 2 of 3" })).toBeInTheDocument();
    expect(within(review()).getByText(claim2.claim_text)).toBeInTheDocument();
    expect(router.state.location.search).toBe(`?claim=${claim2.id}`);
  });

  it("opens the claim named in the URL", async () => {
    open(claim3.id);
    expect(await screen.findByRole("heading", { name: "Claim 3 of 3" })).toBeInTheDocument();
  });

  it("filters claims without hiding unsupported ones", async () => {
    const { user } = open();
    await screen.findByRole("heading", { name: "Claim 1 of 3" });
    await user.click(within(sidebar()).getByRole("button", { name: /Needs attention/ }));
    expect(within(sidebar()).getAllByRole("listitem")).toHaveLength(2);
    await user.click(within(sidebar()).getByRole("button", { name: /^Reviewed/ }));
    expect(within(sidebar()).getByText("No claims match this filter.")).toBeInTheDocument();
  });
});

describe("Review workspace — AI assessment and evidence", () => {
  it("shows the AI assessment apart from the decision, which starts unselected", async () => {
    open(claim2.id);
    await screen.findByRole("heading", { name: "Claim 2 of 3" });
    const ai = screen.getByRole("region", { name: "AI assessment" });
    expect(within(ai).getByText("Partially supported")).toBeInTheDocument();
    expect(within(ai).getByText("High confidence")).toBeInTheDocument();
    expect(within(ai).getByText("Based only on the evidence shown.")).toBeInTheDocument();
    expect(within(ai).queryByText(/gpt|groq/i)).not.toBeInTheDocument(); // no model branding
    for (const name of ["Keep", "Qualify", "Replace", "Remove"]) {
      expect(decision(name)).toHaveAttribute("aria-checked", "false");
    }
  });

  it("explains the figure mismatch with readable labels and both values", async () => {
    open(claim2.id);
    const issues = await screen.findByRole("region", { name: /Issues detected/ });
    expect(within(issues).getByText("Figure mismatch")).toBeInTheDocument();
    expect(within(issues).getByText("22% lower odds")).toBeInTheDocument();
    expect(within(issues).getByText("OR 0.81 (~19% lower odds)")).toBeInTheDocument();
    expect(within(issues).queryByText("FIGURE_MISMATCH")).not.toBeInTheDocument();
  });

  it("puts evidence used in the assessment first and frames the rest as relevance only", async () => {
    open(claim2.id);
    await screen.findByRole("heading", { name: "Claim 2 of 3" });
    const panel = screen.getByRole("region", { name: "Evidence" });
    expect(within(panel).getByRole("heading", { name: /Remote Patient Monitoring in Heart Failure/ })).toBeInTheDocument();
    const doi = within(panel).getByRole("link", { name: /doi:10\.1002\/ejhf\.3568/ });
    expect(doi).toHaveAttribute("href", "https://doi.org/10.1002/ejhf.3568");
    expect(doi).toHaveAttribute("target", "_blank");
    expect(within(panel).getByText("Assessment based on the public abstract.")).toBeInTheDocument();

    const usedHeading = within(panel).getByRole("heading", { name: "Used in assessment" });
    const usedList = usedHeading.nextElementSibling as HTMLElement;
    expect(within(usedList).getAllByRole("listitem")).toHaveLength(1);
    expect(usedList.textContent).toContain("pooled odds ratio [OR] 0.81");
    expect(within(usedList).getByText("0.81").tagName).toBe("MARK"); // matching figure highlighted

    const additional = within(panel).getByText("Additional retrieved passages (3)").closest("details")!;
    expect(additional).not.toHaveAttribute("open");
    expect(within(additional).getByText("Retrieved by relevance; not necessarily supporting.")).toBeInTheDocument();
  });

  it("shows an honest empty state when evidence is unavailable", async () => {
    const unavailable = {
      ...claim3,
      id: "c-unavailable",
      evidence: [],
      evidence_availability: {
        status: "UNAVAILABLE" as const,
        message: "Full supporting evidence is unavailable: the source's text could not be accessed. Assessment limited to available metadata.",
      },
      assessment: {
        ...claim3.assessment!,
        verdict: "UNVERIFIABLE" as const,
        confidence_level: null,
        issues: [{ type: "EVIDENCE_UNAVAILABLE" as const, description: "No public abstract is available for the cited source.", claim_value: null, evidence_value: null }],
        suggested_revision: null,
        evidence_ids: [],
      },
    };
    setup(`/review/proj-1?claim=c-unavailable`, { seeded: true, claims: [claim1, unavailable] });
    await screen.findByRole("heading", { name: "Claim 2 of 2" });
    const ai = screen.getByRole("region", { name: "AI assessment" });
    expect(within(ai).getByText("Unverifiable")).toBeInTheDocument();
    expect(within(ai).getByText(/No AI judgement/)).toBeInTheDocument();
    expect(screen.getByText("Evidence unavailable", { selector: "h4, li h4" })).toBeInTheDocument();
    const panel = screen.getByRole("region", { name: "Evidence" });
    expect(within(panel).getByRole("heading", { name: "Evidence unavailable" })).toBeInTheDocument();
    expect(within(panel).getByText(/could not be accessed/)).toBeInTheDocument();
    expect(within(panel).queryByRole("heading", { name: "Used in assessment" })).not.toBeInTheDocument();
  });
});

describe("Review workspace — decisions", () => {
  it("Use suggestion fills the revised claim and selects Qualify, without saving", async () => {
    const { user, backend } = open(claim2.id);
    await screen.findByRole("heading", { name: "Claim 2 of 3" });
    await user.click(screen.getByRole("button", { name: "Use suggestion" }));
    expect(decision("Qualify")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByLabelText(/Revised claim/)).toHaveValue(claim2.assessment!.suggested_revision);
    await user.type(screen.getByLabelText(/Revised claim/), " (edited)");
    expect(screen.getByLabelText(/Revised claim/)).toHaveValue(`${claim2.assessment!.suggested_revision} (edited)`);
    expect(backend.state.calls.saveReview).toHaveLength(0);
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });

  it("Use suggestion keeps an existing decision", async () => {
    const { user } = open(claim2.id);
    await screen.findByRole("heading", { name: "Claim 2 of 3" });
    await user.click(decision("Replace"));
    await user.click(screen.getByRole("button", { name: "Use suggestion" }));
    expect(decision("Replace")).toHaveAttribute("aria-checked", "true");
  });

  it("Replace requires a revised claim; Qualify makes it optional; Keep hides it", async () => {
    const { user } = open(claim2.id);
    await screen.findByRole("heading", { name: "Claim 2 of 3" });
    await user.click(decision("Replace"));
    expect(screen.getByText("Replace needs the replacement wording.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save decision" })).toBeDisabled();
    await user.click(decision("Qualify"));
    expect(screen.getByText("Revised claim").parentElement).toHaveTextContent("Optional");
    expect(screen.getByRole("button", { name: "Save decision" })).toBeEnabled();
    await user.click(decision("Keep"));
    expect(screen.queryByLabelText(/Revised claim/)).not.toBeInTheDocument();
  });

  it("supports arrow-key selection in the decision group", async () => {
    const { user } = open(claim2.id);
    await screen.findByRole("heading", { name: "Claim 2 of 3" });
    decision("Keep").focus();
    await user.keyboard("{ArrowRight}");
    expect(decision("Qualify")).toHaveAttribute("aria-checked", "true");
    expect(decision("Qualify")).toHaveFocus();
  });

  it("Save waits for the server, then shows the claim as reviewed and updates progress", async () => {
    const { user, backend } = open(claim1.id);
    await screen.findByRole("heading", { name: "Claim 1 of 3" });
    await user.click(decision("Keep"));
    await user.type(screen.getByLabelText(/Reviewer note/), "Matches the abstract.");
    await user.click(screen.getByRole("button", { name: "Save decision" }));

    await waitFor(() => expect(screen.getByText(/^Saved /)).toBeInTheDocument());
    expect(backend.state.calls.saveReview).toEqual([
      { claimId: claim1.id, body: { decision: "KEEP", reviewer_note: "Matches the abstract.", revised_claim: null } },
    ]);
    const first = within(sidebar()).getAllByRole("listitem")[0]!;
    expect(within(first).getByText("Reviewed · Keep")).toBeInTheDocument();
    expect(within(sidebar()).getByText("1 of 3 reviewed")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Claim 1 of 3" })).toBeInTheDocument(); // Save does not navigate
  });

  it("Save & next moves on immediately and marks the previous claim Saving… until confirmed", async () => {
    const { user, backend } = open(claim1.id);
    backend.state.saveDelayMs = 150;
    await screen.findByRole("heading", { name: "Claim 1 of 3" });
    await user.click(decision("Keep"));
    await user.click(screen.getByRole("button", { name: /Save & next/ }));

    expect(screen.getByRole("heading", { name: "Claim 2 of 3" })).toBeInTheDocument();
    const first = within(sidebar()).getAllByRole("listitem")[0]!;
    expect(within(first).getByText("Saving…")).toBeInTheDocument();
    expect(within(first).queryByText(/Reviewed/)).not.toBeInTheDocument(); // not before the server confirms
    expect(await within(first).findByText("Reviewed · Keep")).toBeInTheDocument();
    expect(within(sidebar()).getByText("1 of 3 reviewed")).toBeInTheDocument();
  });

  it("a failed Save & next returns to the claim with the reviewer's input restored", async () => {
    const { user, backend } = open(claim2.id);
    backend.state.saveFailures.set(claim2.id, { status: 503, code: "database_unavailable" });
    await screen.findByRole("heading", { name: "Claim 2 of 3" });
    await user.click(screen.getByRole("button", { name: "Use suggestion" }));
    await user.type(screen.getByLabelText(/Reviewer note/), "Corrected to 19%.");
    await user.click(screen.getByRole("button", { name: /Save & next/ }));

    expect(await within(sidebar()).findByText("Save failed")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Claim 2 of 3" })).toBeInTheDocument();
    expect(decision("Qualify")).toHaveAttribute("aria-checked", "true");
    expect(screen.getByLabelText(/Reviewer note/)).toHaveValue("Corrected to 19%.");
    expect(screen.getByLabelText(/Revised claim/)).toHaveValue(claim2.assessment!.suggested_revision);
    expect(screen.getByText(/temporarily unavailable/)).toBeInTheDocument();

    backend.state.saveFailures.clear();
    await user.click(screen.getByRole("button", { name: /Save & next/ }));
    expect(await screen.findByRole("heading", { name: "Claim 3 of 3" })).toBeInTheDocument();
    await waitFor(() => expect(within(within(sidebar()).getAllByRole("listitem")[1]!).getByText("Reviewed · Qualify")).toBeInTheDocument());
  });

  it("does not send duplicate saves for the same claim", async () => {
    const { user, backend } = open(claim1.id);
    backend.state.saveDelayMs = 100;
    await screen.findByRole("heading", { name: "Claim 1 of 3" });
    await user.click(decision("Keep"));
    const save = screen.getByRole("button", { name: "Save decision" });
    await user.click(save);
    await user.click(save);
    await waitFor(() => expect(screen.getByText(/^Saved /)).toBeInTheDocument());
    expect(backend.state.calls.saveReview).toHaveLength(1);
  });
});

describe("Review workspace — unsaved changes", () => {
  it("asks before discarding, and can keep editing", async () => {
    const { user } = open(claim1.id);
    await screen.findByRole("heading", { name: "Claim 1 of 3" });
    await user.click(decision("Remove"));
    await user.click(within(sidebar()).getByText(claim2.claim_text));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Discard unsaved changes?")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(screen.getByRole("heading", { name: "Claim 1 of 3" })).toBeInTheDocument();
    expect(decision("Remove")).toHaveAttribute("aria-checked", "true");

    await user.click(within(sidebar()).getByText(claim2.claim_text));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Discard changes" }));
    expect(await screen.findByRole("heading", { name: "Claim 2 of 3" })).toBeInTheDocument();
    await user.click(within(sidebar()).getByText(claim1.claim_text));
    expect(await screen.findByRole("heading", { name: "Claim 1 of 3" })).toBeInTheDocument();
    expect(decision("Remove")).toHaveAttribute("aria-checked", "false"); // discarded
  });

  it("switching claims without edits needs no confirmation", async () => {
    const { user } = open(claim1.id);
    await screen.findByRole("heading", { name: "Claim 1 of 3" });
    await user.click(within(sidebar()).getByText(claim3.claim_text));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Claim 3 of 3" })).toBeInTheDocument();
  });
});

describe("Review workspace — reassessment and failures", () => {
  it("reassesses a claim and keeps the human review", async () => {
    const { user, backend } = open(claim2.id);
    backend.state.reassessResult = (c) => ({ ...c, assessment: { ...c.assessment!, id: "assess-new", explanation: "Re-run explanation." } });
    await screen.findByRole("heading", { name: "Claim 2 of 3" });
    await user.click(screen.getByRole("button", { name: "Reassess" }));
    expect(await screen.findByText("Re-run explanation.")).toBeInTheDocument();
    expect(backend.state.calls.reassess).toBe(1);
  });

  it("shows a reassessment failure without discarding the current assessment", async () => {
    const { user, backend } = open(claim2.id);
    backend.state.reassessFailure = { status: 503, code: "llm_rate_limited" };
    await screen.findByRole("heading", { name: "Claim 2 of 3" });
    await user.click(screen.getByRole("button", { name: "Reassess" }));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Reassessment didn't complete")).toBeInTheDocument();
    expect(within(alert).getByText(/temporarily rate limited/)).toBeInTheDocument();
    expect(screen.getByText(claim2.assessment!.explanation)).toBeInTheDocument();
  });

  it("isolates a claim whose assessment failed and offers a retry", async () => {
    const failed = { ...claim3, id: "c-failed", status: "ERROR" as const, assessment: null, processing_error: "The AI provider timed out after 60s.", evidence: [] };
    const { user, backend } = setup(`/review/proj-1?claim=c-failed`, { seeded: true, claims: [claim1, failed] });
    backend.state.reassessResult = (c) => ({ ...c, assessment: claim3.assessment, evidence: claim3.evidence });
    const status = await screen.findByRole("status", { name: "" }).catch(() => screen.getByText("Assessment couldn't be completed"));
    expect(status).toBeTruthy();
    expect(screen.getByText(/The AI provider timed out after 60s/)).toBeInTheDocument();
    expect(within(sidebar()).getByText("Assessment failed")).toBeInTheDocument();
    // The researcher can still decide without an AI assessment.
    expect(decision("Keep")).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Retry assessment" }));
    expect(await screen.findByRole("region", { name: "AI assessment" })).toBeInTheDocument();
  });

  it("handles an unknown review id", async () => {
    setup("/review/nope");
    expect(await screen.findByRole("heading", { name: "Review not found" })).toBeInTheDocument();
  });
});

describe("Review workspace — long content", () => {
  it("wraps long text everywhere and keeps the save bar outside the scrolling content", async () => {
    const sentence = "Remote patient monitoring was associated with lower odds of first heart-failure hospitalization in adults with reduced ejection fraction, across programmes combining telemonitoring, structured telephone support and nurse-led education";
    const long = `${sentence}, ${sentence.toLowerCase()}.`;
    const token = "10.1002/ejhf.3568-an-unbroken-identifier-" + "x".repeat(120);
    const base = claim2.assessment!;
    const longClaim = {
      ...claim2,
      claim_text: long,
      sources: [{ ...claim2.sources[0]!, title: `${claim2.sources[0]!.title}: ${sentence}` }],
      evidence: claim2.evidence.map((e, i) => (i === 0 ? { ...e, passage: `${e.passage} ${sentence}. ${token}` } : e)),
      assessment: {
        ...base,
        explanation: `${base.explanation} ${sentence}. ${sentence}.`,
        suggested_revision: `${base.suggested_revision} ${sentence}.`,
        issues: Array.from({ length: 6 }, (_, i) => ({ ...base.issues[0]!, description: `${i + 1}. ${base.issues[0]!.description} ${sentence}.` })),
      },
      review: { id: "r-1", decision: "QUALIFY" as const, reviewer_note: `${sentence}. ${sentence}. ${token}`, revised_claim: `${sentence}.`, reviewed_at: "2026-10-19T12:00:00Z", created_at: "2026-10-19T12:00:00Z", updated_at: "2026-10-19T12:00:00Z" },
      review_status: "REVIEWED" as const,
    };
    setup(`/review/proj-1?claim=${claim2.id}`, { seeded: true, claims: [claim1, longClaim, claim3] });
    await screen.findByRole("heading", { name: "Claim 2 of 3" });

    const claimText = within(review()).getByText(long);
    expect(claimText).toHaveClass("text-wrap-anywhere");
    expect(screen.getAllByText("Figure mismatch")).toHaveLength(6);
    expect(screen.getByLabelText(/Reviewer note/)).toHaveValue(longClaim.review.reviewer_note);
    expect(screen.getByLabelText(/Revised claim/)).toHaveValue(longClaim.review.revised_claim);

    const panel = screen.getByRole("region", { name: "Evidence" });
    expect(within(panel).getByRole("heading", { name: longClaim.sources[0]!.title })).toHaveClass("text-wrap-anywhere");
    expect(within(panel).getByText(new RegExp(token)).closest("blockquote")).toHaveClass("text-wrap-anywhere");

    // The action bar is a sibling of the scroll container, never overlaid on it.
    const saveBar = screen.getByRole("button", { name: "Save decision" }).closest("footer")!;
    const scroller = claimText.closest(".overflow-y-auto")!;
    expect(scroller).not.toContainElement(saveBar);
    expect(scroller).toHaveClass("overflow-x-hidden");
    for (const field of [screen.getByLabelText(/Reviewer note/), screen.getByLabelText(/Revised claim/), screen.getByRole("region", { name: "AI suggested revision" })]) {
      expect(scroller).toContainElement(field);
    }
  });
});
