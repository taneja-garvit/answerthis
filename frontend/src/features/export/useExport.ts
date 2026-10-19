import { useMutation } from "@tanstack/react-query";

import { fetchExport, type ExportFormat } from "../../api/exports";

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  // Give the browser a moment to start the download before revoking.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function useExport(projectId: string) {
  return useMutation({
    mutationFn: async (format: ExportFormat) => {
      const { blob, filename } = await fetchExport(projectId, format);
      triggerDownload(blob, filename ?? `evidence-review.${format}`);
      return format;
    },
  });
}
