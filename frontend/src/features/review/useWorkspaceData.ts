import { useQuery } from "@tanstack/react-query";

import { getDraftClaims } from "../../api/drafts";
import { getProject } from "../../api/projects";
import { queryKeys } from "../../api/queryKeys";
import type { DraftSummary } from "../../api/types";

/** Project → its latest draft → that draft's claims (one composite request). */
export function useWorkspaceData(projectId: string) {
  const project = useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: ({ signal }) => getProject(projectId, signal),
    // While the server is still analyzing (e.g. after a reload mid-analysis),
    // check back until it finishes.
    refetchInterval: (query) =>
      query.state.data?.drafts.some((d) => d.analysis_status === "ANALYZING") ? 5000 : false,
  });

  const draft: DraftSummary | undefined = project.data?.drafts.at(-1);
  const claims = useQuery({
    queryKey: queryKeys.draftClaims(draft?.id ?? "none"),
    queryFn: ({ signal }) => getDraftClaims(draft!.id, signal),
    enabled: Boolean(draft) && draft?.analysis_status !== "ANALYZING",
  });

  return { project, draft, claims };
}
