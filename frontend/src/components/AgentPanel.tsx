// frontend/src/components/AgentPanel.tsx
// One card per agent for Live Monitor's panel grid. With 10 agents (v2.1
// pipeline), a fixed 2x2 grid doesn't fit — this renders as a responsive
// grid that wraps instead, per the note in AGENTX_Build_Plan.md about
// Live Monitor needing a redesign before it's built.
import type { AgentRun } from "../types";
import { StatusPill } from "./StatusPill";
import "./AgentPanel.css";

interface AgentPanelProps {
  run: AgentRun;
}

export function AgentPanel({ run }: AgentPanelProps) {
  const progressPct = run.step_total > 0 ? Math.round((run.step_current / run.step_total) * 100) : 0;

  return (
    <div className={`agent-panel agent-panel--${run.status}`}>
      <div className="agent-panel__header">
        <span className="agent-panel__name">{run.agent_name.replace(/_/g, " ")}</span>
        <StatusPill status={run.status} />
      </div>

      <p className="agent-panel__subtask">{run.current_subtask ?? "Idle"}</p>

      {run.step_total > 0 && (
        <div className="agent-panel__progress">
          <div className="agent-panel__progress-bar" style={{ width: `${progressPct}%` }} />
        </div>
      )}

      {run.duration_ms != null && (
        <span className="agent-panel__duration">{(run.duration_ms / 1000).toFixed(1)}s</span>
      )}
    </div>
  );
}
