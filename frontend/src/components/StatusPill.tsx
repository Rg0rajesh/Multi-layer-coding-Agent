// frontend/src/components/StatusPill.tsx
// One status vocabulary reused by Dashboard, LiveMonitor, and History.
// Fill = actively running/done, outline = pending/idle, dashed = failed —
// weight differentiates instead of color, per the B&W spec.
import "./StatusPill.css";

const LABELS: Record<string, string> = {
  pending: "Pending",
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

interface StatusPillProps {
  status: string;
}

export function StatusPill({ status }: StatusPillProps) {
  const label = LABELS[status] ?? status;
  return <span className={`status-pill status-pill--${status}`}>{label}</span>;
}
