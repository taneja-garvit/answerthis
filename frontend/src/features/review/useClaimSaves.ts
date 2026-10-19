import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";

import { queryKeys } from "../../api/queryKeys";
import { saveReview } from "../../api/reviews";
import type { Claim, DraftClaims, ReviewInput } from "../../api/types";
import { toUserError, type UserFacingError } from "../../lib/errors";

export type SaveState = { status: "saving" } | { status: "error"; error: UserFacingError };

export function replaceClaim(data: DraftClaims | undefined, claim: Claim): DraftClaims | undefined {
  if (!data) return data;
  return { ...data, claims: data.claims.map((c) => (c.id === claim.id ? claim : c)) };
}

/** Review saves tracked per claim. A claim only becomes Reviewed when the
 *  server's response is written into the cache; until then it is "saving". */
export function useClaimSaves(draftId: string | undefined, projectId: string) {
  const queryClient = useQueryClient();
  const [saves, setSaves] = useState<Record<string, SaveState>>({});
  const inFlight = useRef(new Set<string>());

  const save = useCallback(
    async (claimId: string, input: ReviewInput): Promise<Claim> => {
      if (inFlight.current.has(claimId)) throw new Error("save already in progress");
      inFlight.current.add(claimId);
      setSaves((s) => ({ ...s, [claimId]: { status: "saving" } }));
      try {
        const claim = await saveReview(claimId, input);
        if (draftId) {
          queryClient.setQueryData<DraftClaims>(queryKeys.draftClaims(draftId), (data) =>
            replaceClaim(data, claim),
          );
        }
        void queryClient.invalidateQueries({ queryKey: queryKeys.progress(projectId) });
        setSaves(({ [claimId]: _done, ...rest }) => rest);
        return claim;
      } catch (error) {
        setSaves((s) => ({ ...s, [claimId]: { status: "error", error: toUserError(error) } }));
        throw error;
      } finally {
        inFlight.current.delete(claimId);
      }
    },
    [draftId, projectId, queryClient],
  );

  const clearError = useCallback(
    (claimId: string) =>
      setSaves((s) => {
        if (s[claimId]?.status !== "error") return s;
        const { [claimId]: _cleared, ...rest } = s;
        return rest;
      }),
    [],
  );

  return { saves, save, clearError };
}
