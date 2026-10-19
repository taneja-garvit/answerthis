export function ProgressBar({ value, total, label }: { value: number; total: number; label: string }) {
  const percent = total ? Math.round((value / total) * 100) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={value}
      aria-valuetext={`${value} of ${total} reviewed`}
      className="h-1 w-full overflow-hidden rounded-full bg-line"
    >
      <div className="h-full rounded-full bg-accent transition-[width] duration-300" style={{ width: `${percent}%` }} />
    </div>
  );
}
