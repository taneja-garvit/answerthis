import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";

import { analyzeDraft, createDraft } from "../../api/drafts";
import { createProject } from "../../api/projects";
import { queryKeys } from "../../api/queryKeys";
import type { AnalysisResult, DraftClaims, Project } from "../../api/types";
import { titleFromDraft } from "../../lib/format";

interface Pending {
  text: string;
  project: Project;
  draftId: string | null;
}

/** Create project → create draft → analyze. If analysis fails, a retry with
 *  the same text reuses the project and draft (drafts are immutable, so edited
 *  text starts a fresh project instead). */
export function useStartReview() {
  const queryClient = useQueryClient();
  const pending = useRef<Pending | null>(null);

  return useMutation({
    mutationFn: async (text: string): Promise<{ project: Project; result: AnalysisResult }> => {
      let current = pending.current;
      if (!current || current.text !== text) {
        current = { text, project: await createProject(titleFromDraft(text)), draftId: null };
        pending.current = current;
      }
      if (!current.draftId) {
        current.draftId = (await createDraft(current.project.id, text)).id;
      }
      return { project: current.project, result: await analyzeDraft(current.draftId) };
    },
    onSuccess: ({ project, result }) => {
      pending.current = null;
      // Seed the workspace's queries so it renders without another round trip.
      queryClient.setQueryData<DraftClaims>(queryKeys.draftClaims(result.draft_id), {
        draft_id: result.draft_id,
        project_id: result.project_id,
        claims: result.claims,
      });
      queryClient.setQueryData<Project>(queryKeys.project(project.id), {
        ...project,
        drafts: [
          {
            id: result.draft_id,
            char_count: 0,
            claim_count: result.claims.length,
            analysis_status: result.analysis_status,
            created_at: project.created_at,
          },
        ],
      });
    },
  });
}
