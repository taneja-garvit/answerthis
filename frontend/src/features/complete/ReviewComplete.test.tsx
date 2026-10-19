import { screen, waitFor, within } from "@testing-library/react";

import { liveClaims } from "../../test/mockBackend";
import { setup } from "../../test/render";

const [claim1, claim2, claim3] = liveClaims as [typeof liveClaims[0], typeof liveClaims[0], typeof liveClaims[0]];
const decision = (name: string) => screen.getByRole("radio", { name });

describe("Heart-failure journey to completion", () => {
  it("reviews all three claims and lands on a summary that keeps AI and human counts separate", async () => {
    const { user, router, backend } = setup(`/review/proj-1`, { seeded: true });

    await screen.findByRole("heading", { name: "Claim 1 of 3" });
    await user.click(decision("Keep"));
    await user.click(screen.getByRole("button", { name: /Save & next/ }));

    await screen.findByRole("heading", { name: "Claim 2 of 3" });
    await user.click(screen.getByRole("button", { name: "Use suggestion" }));
    await user.type(screen.getByLabelText(/Reviewer note/), "Corrected mortality effect from 22% to approximately 19% lower odds.");
    await user.click(screen.getByRole("button", { name: /Save & next/ }));

    await screen.findByRole("heading", { name: "Claim 3 of 3" });
    await user.click(decision("Remove"));
    await user.type(screen.getByLabelText(/Reviewer note/), "Source supports an average effect across studied populations, not every patient.");
    await user.click(screen.getByRole("button", { name: /Save & finish/ }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/review/proj-1/complete"));
    expect(await screen.findByRole("heading", { name: "Review complete" })).toBeInTheDocument();
    expect(screen.getByText(/3 of 3 claims reviewed/)).toBeInTheDocument();

    const human = screen.getByRole("region", { name: "Your decisions" });
    const ai = screen.getByRole("region", { name: "AI assessments" });
    const count = (region: HTMLElement, label: string) => within(region).getByText(label).parentElement!.lastElementChild!.textContent;
    expect([count(human, "Keep"), count(human, "Qualify"), count(human, "Replace"), count(human, "Remove")]).toEqual(["1", "1", "0", "1"]);
    expect([count(ai, "Supported"), count(ai, "Partially supported"), count(ai, "Unsupported"), count(ai, "Unverifiable")]).toEqual(["1", "1", "1", "0"]);

    expect(backend.state.calls.saveReview.map((c) => [c.claimId, c.body.decision])).toEqual([
      [claim1.id, "KEEP"], [claim2.id, "QUALIFY"], [claim3.id, "REMOVE"],
    ]);
    expect(backend.state.calls.saveReview[1]!.body.revised_claim).toBe(claim2.assessment!.suggested_revision);
    expect(screen.getByText(claim2.assessment!.suggested_revision!)).toBeInTheDocument(); // revised wording listed

    const createUrl = vi.spyOn(URL, "createObjectURL");
    await user.click(screen.getByRole("button", { name: "Export CSV" }));
    await screen.findByText("CSV audit trail downloaded.");
    await user.click(screen.getByRole("button", { name: "Export JSON" }));
    await screen.findByText("JSON audit trail downloaded.");
    expect(backend.state.calls.exports).toEqual(["csv", "json"]);
    expect(createUrl).toHaveBeenCalledTimes(2);

    await user.click(screen.getByRole("link", { name: "Return to review" }));
    expect(await screen.findByText("All claims reviewed. Decisions remain editable.")).toBeInTheDocument();
  });

  it("does not claim completion while claims still need review", async () => {
    setup(`/review/proj-1/complete`, { seeded: true });
    expect(await screen.findByRole("heading", { name: "Review in progress" })).toBeInTheDocument();
    expect(screen.getByText("3 of 3 claims still need a decision.")).toBeInTheDocument();
  });

  it("reports an export failure", async () => {
    const { user, backend } = setup(`/review/proj-1`, { seeded: true });
    backend.state.exportFailure = { status: 500, code: "internal_error" };
    await screen.findByRole("heading", { name: "Claim 1 of 3" });
    await user.click(screen.getByRole("button", { name: /Export/ }));
    await user.click(screen.getByRole("menuitem", { name: /Export JSON/ }));
    expect(await screen.findByText(/Export failed/)).toBeInTheDocument();
  });
});
