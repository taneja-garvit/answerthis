import { ChevronDown, Download } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import type { ExportFormat } from "../../api/exports";
import { Button } from "../../components/Button";
import { toUserError } from "../../lib/errors";
import { useExport } from "./useExport";

const OPTIONS: { format: ExportFormat; label: string; hint: string }[] = [
  { format: "csv", label: "Export CSV", hint: "One row per claim" },
  { format: "json", label: "Export JSON", hint: "Full audit trail with history" },
];

export function ExportMenu({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(false);
  const exporter = useExport(projectId);
  const menuId = useId();
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <Button
        size="sm"
        variant="secondary"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => {
          exporter.reset();
          setOpen((o) => !o);
        }}
        loading={exporter.isPending}
        icon={<Download className="size-3.5" aria-hidden />}
      >
        Export
        <ChevronDown className="size-3.5 text-ink-3" aria-hidden />
      </Button>
      {open && (
        <div
          id={menuId}
          role="menu"
          className="absolute right-0 z-30 mt-1.5 w-60 rounded-md border border-line bg-surface p-1 shadow-[0_8px_24px_rgba(30,28,25,0.12)]"
        >
          {OPTIONS.map((option) => (
            <button
              key={option.format}
              role="menuitem"
              type="button"
              className="flex w-full flex-col rounded-[5px] px-3 py-2 text-left hover:bg-subtle"
              onClick={() => {
                setOpen(false);
                exporter.mutate(option.format);
              }}
            >
              <span className="font-medium text-ink">{option.label}</span>
              <span className="text-xs text-ink-3">{option.hint}</span>
            </button>
          ))}
        </div>
      )}
      {exporter.isError && (
        <p role="alert" className="absolute right-0 mt-1.5 w-64 rounded-md border border-unsupported-line bg-danger-soft px-3 py-2 text-xs text-ink-2">
          Export failed. {toUserError(exporter.error).message}
        </p>
      )}
    </div>
  );
}
