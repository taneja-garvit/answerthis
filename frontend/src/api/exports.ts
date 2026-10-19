import { apiDownload } from "./client";

export type ExportFormat = "csv" | "json";

export const fetchExport = (projectId: string, format: ExportFormat) =>
  apiDownload(`/api/projects/${projectId}/export?format=${format}`);
