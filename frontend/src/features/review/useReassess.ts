import { useMutation, useQueryClient } from "@tanstack/react-query";

import { getClaim, reassessClaim } from "../../api/claims";
import { queryKeys } from "../../api/queryKeys";
import type { DraftClaims } from "../../api/types";
import { replaceClaim } from "./useClaimSaves";

export function useReassess(draftId: string | undefined) {
  const queryClient = useQueryClient();
  const write = (claim: Parameters<typeof replaceClaim>[1]) => {
    if (draftId) {
      queryClient.setQueryData<DraftClaims>(queryKeys.draftClaims(draftId), (data) =>
        replaceClaim(data, claim),
      );
    }
  };

  return useMutation({
    mutationFn: (claimId: string) => reassessClaim(claimId),
    onSuccess: write,
    onError: async (_error, claimId) => {
      // The server records why reassessment failed (processing_error) and keeps
      // the previous assessment; pick that up without discarding anything.
      try {
        write(await getClaim(claimId));
      } catch {
        // The original error is still shown; nothing else to do.
      }
    },
  });
}
