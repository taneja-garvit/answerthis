import { apiRequest } from "./client";
import type { Progress, Project } from "./types";

export const createProject = (title: string) =>
  apiRequest<Project>("/api/projects", { method: "POST", body: { title } });

export const getProject = (projectId: string, signal?: AbortSignal) =>
  apiRequest<Project>(`/api/projects/${projectId}`, { signal });

export const getProgress = (projectId: string, signal?: AbortSignal) =>
  apiRequest<Progress>(`/api/projects/${projectId}/progress`, { signal });
