import { screen, waitFor, within } from "@testing-library/react";

import { EXAMPLE_DRAFT } from "../../lib/exampleDraft";
import { setup } from "../../test/render";

describe("Draft input", () => {
  it("loads the heart-failure example into the editor without creating anything", async () => {
    const { user, backend } = setup("/");
    expect(screen.getByRole("heading", { name: "Review a research draft" })).toBeInTheDocument();
    const analyze = screen.getByRole("button", { name: "Analyze draft" });
    expect(analyze).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Load example" }));

    expect(screen.getByLabelText("Research draft")).toHaveValue(EXAMPLE_DRAFT);
    expect(analyze).toBeEnabled();
    expect(screen.getByText(`${EXAMPLE_DRAFT.length.toLocaleString()} / 20,000`)).toBeInTheDocument();
    expect(backend.state.calls.createProject).toBe(0);
  });

  it("runs project → draft → analyze, shows an honest loading state, then opens the workspace", async () => {
    const { user, backend, router } = setup("/");
    backend.state.analyzeDelayMs = 50;
    await user.click(screen.getByRole("button", { name: "Load example" }));
    await user.click(screen.getByRole("button", { name: "Analyze draft" }));

    const loading = await screen.findByRole("heading", { name: "Analyzing your draft" });
    expect(loading).toBeInTheDocument();
    expect(screen.getByText(/Extracting claims, resolving sources and checking evidence/)).toBeInTheDocument();
    const panel = loading.closest("section")!;
    expect(panel.textContent).not.toMatch(/\d+\s?%/); // no fake percentages
    expect(screen.getByRole("button", { name: /Analyzing/ })).toBeDisabled();
    expect(screen.getByLabelText("Research draft")).toHaveAttribute("readonly");

    await waitFor(() => expect(router.state.location.pathname).toBe("/review/proj-1"));
    expect(backend.state.calls).toMatchObject({ createProject: 1, createDraft: 1, analyze: 1 });
    expect(await screen.findByRole("heading", { name: /^Claim 1 of 3$/ })).toBeInTheDocument();
  });

  it("preserves the draft on failure and retries without creating a second project", async () => {
    const { user, backend } = setup("/");
    backend.state.analyzeFailure = { status: 503, code: "llm_rate_limited" };
    await user.click(screen.getByLabelText("Research draft"));
    await user.paste("Drug A lowered blood pressure in adults [1].");
    await user.click(screen.getByRole("button", { name: "Analyze draft" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Analysis didn't complete")).toBeInTheDocument();
    expect(within(alert).getByText("The AI provider is temporarily rate limited. Try again shortly.")).toBeInTheDocument();
    expect(within(alert).getByText(/req-test-1/)).toBeInTheDocument();
    expect(screen.getByLabelText("Research draft")).toHaveValue("Drug A lowered blood pressure in adults [1].");

    backend.state.analyzeFailure = null;
    await user.click(within(alert).getByRole("button", { name: "Retry analysis" }));
    await screen.findByRole("heading", { name: /^Claim 1 of 3$/ });
    expect(backend.state.calls).toMatchObject({ createProject: 1, createDraft: 1, analyze: 2 });
  });

  it("explains an unreachable API without leaking internals", async () => {
    const { user } = setup("/");
    // No handler for this origin path → MSW returns a network error.
    const { server } = await import("../../test/server");
    const { http, HttpResponse } = await import("msw");
    server.use(http.post("http://localhost:8000/api/projects", () => HttpResponse.error()));
    await user.click(screen.getByLabelText("Research draft"));
    await user.paste("Some claim with evidence [1].");
    await user.click(screen.getByRole("button", { name: "Analyze draft" }));
    expect(await screen.findByText(/couldn't reach the review service/)).toBeInTheDocument();
  });

  it("blocks drafts over the length limit", async () => {
    const { user } = setup("/");
    const editor = screen.getByLabelText("Research draft");
    await user.click(editor);
    await user.paste("x".repeat(20_001));
    expect(screen.getByText(/longer than the 20,000-character limit/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze draft" })).toBeDisabled();
    expect(editor).toHaveAttribute("aria-invalid", "true");
  });
});
