// frontend/src/components/LogStream.tsx
// Renders the [HH:MM:SS] [AGENT] › message format from the Frontend
// Spec's log-format appendix. Severity reads through font-weight and the
// prefix glyph, never color — ERROR lines get the heaviest weight, WARN
// a medium weight with an outlined glyph, everything else stays regular.
import { useEffect, useRef } from "react";
import type { AgentLogLine } from "../hooks/useAgentStream";
import "./LogStream.css";

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-US", { hour12: false });
  } catch {
    return "--:--:--";
  }
}

interface LogStreamProps {
  lines: AgentLogLine[];
  autoScroll?: boolean;
  emptyLabel?: string;
}

export function LogStream({ lines, autoScroll = true, emptyLabel = "Waiting for agent activity…" }: LogStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ block: "end" });
  }, [lines.length, autoScroll]);

  if (lines.length === 0) {
    return <div className="log-stream log-stream--empty">{emptyLabel}</div>;
  }

  return (
    <div className="log-stream" role="log" aria-live="polite">
      {lines.map((line) => (
        <div key={line.id} className={`log-line log-line--${line.level.toLowerCase()}`}>
          <span className="log-line__time">{formatTime(line.timestamp)}</span>
          <span className="log-line__agent">{line.agent}</span>
          <span className="log-line__mark" aria-hidden="true">
            {line.icon}
          </span>
          <span className="log-line__message">{line.message}</span>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
