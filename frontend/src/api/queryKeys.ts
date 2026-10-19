export const queryKeys = {
  project: (projectId: string) => ["project", projectId] as const,
  draftClaims: (draftId: string) => ["draft-claims", draftId] as const,
  progress: (projectId: string) => ["progress", projectId] as const,
};
