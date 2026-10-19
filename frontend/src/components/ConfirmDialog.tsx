import { useEffect, useRef } from "react";

import { Button } from "./Button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Native <dialog>: focus is trapped and Escape cancels without extra code. */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Keep editing",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    } else if (!open && dialog.open) {
      if (typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
    }
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="confirm-title"
      aria-describedby="confirm-description"
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
      className="m-auto w-[min(26rem,calc(100vw-2rem))] rounded-lg border border-line bg-surface p-0 text-ink shadow-[0_12px_40px_rgba(30,28,25,0.18)] backdrop:bg-ink/30"
    >
      {open && (
        <div className="p-5">
          <h2 id="confirm-title" className="text-lg font-semibold">
            {title}
          </h2>
          <p id="confirm-description" className="mt-1.5 text-ink-2">
            {description}
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" onClick={onCancel} autoFocus>
              {cancelLabel}
            </Button>
            <Button variant="danger" onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </div>
        </div>
      )}
    </dialog>
  );
}
