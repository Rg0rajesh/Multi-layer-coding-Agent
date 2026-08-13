// frontend/src/pages/LiveMonitor.tsx
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Sidebar, AgentPanel, LogStream, HumanApprovalPanel } from "../components";
import { useAgentStream } from "../hooks/useAgentStream";
import { agentsApi, tasksApi } from "../api";
import type { AgentRun, RiskScore, Task } from "../types";
import "./LiveMonitor.css";

const GROUPS: { label: string; agents: string[] }[] = [
  { label: "Governance", agents: ["GUARDRAIL", "IDENTITY_BROKER"] },
  { label: "Core", agents: ["PLANNER", "GROUNDING", "HUMAN", "CODER", "TESTER"] },
  { label: "Quality", agents: ["SECURITY", "REVIEWER", "CONTEXT_CURATOR"] },
];

function placeholderRun(agentName: string): AgentRun {
  return { id: agentName, agent_name: agentName, agent_color: null, status: "pending", current_subtask: null, step_current: 0, step_total: 0, started_at: null, completed_at: null, duration_ms: null };
}

export default function LiveMonitor() {
  const [params] = useSearchParams();
  const taskId = params.get("task");
  const [task, setTask] = useState<Task | null>(null);
  const [runs, setRuns] = useState<Record<string, AgentRun>>({});
  const [risk, setRisk] = useState<RiskScore | null>(null);
  const [humanWaiting, setHumanWaiting] = useState(false);
  const { connectionStatus, lines } = useAgentStream(taskId);

  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;
    tasksApi.get(taskId).then((t) => !cancelled && setTask(t)).catch(() => {});
    agentsApi.runs(taskId).then((list) => { if (!cancelled) setRuns(Object.fromEntries(list.map((r) => [r.agent_name, r]))); }).catch(() => {});
    agentsApi.riskScore(taskId).then((r) => !cancelled && setRisk(r)).catch(() => {});
    return () => { cancelled = true; };
  }, [taskId]);

  useEffect(() => {
    if (!taskId) return;
    const checkApproval = () => agentsApi.pendingPlan(taskId).then((result) => setHumanWaiting(result.pending)).catch(() => setHumanWaiting(false));
    void checkApproval();
    const timer = window.setInterval(checkApproval, 2000);
    return () => window.clearInterval(timer);
  }, [taskId]);

  const mergedRuns = useMemo(() => {
    const merged = { ...runs };
    for (const line of lines) {
      const existing = merged[line.agent] ?? placeholderRun(line.agent);
      const status = line.level === "ERROR" ? "failed" : line.level === "PASS" || line.level === "DONE" ? "completed" : "running";
      merged[line.agent] = { ...existing, status, current_subtask: line.message };
    }
    return merged;
  }, [runs, lines]);

  if (!taskId) {
    return <div className="app-shell"><Sidebar /><main className="app-main"><div className="empty-state"><h3>No task selected</h3><p>Open a task from the Dashboard or History page to watch it live.</p></div></main></div>;
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <div className="page-header">
          <div>
            <h1>{task?.title ?? "Live Monitor"}</h1>
            <p className="page-header__meta">{connectionStatus === "open" ? "Connected — streaming live" : `Connection: ${connectionStatus}`}</p>
          </div>
          {risk && <span className={`live-monitor__risk live-monitor__risk--${risk.last_verdict}`}>Guardrail: {risk.running_score.toFixed(0)}/100 ({risk.last_verdict})</span>}
        </div>

        {humanWaiting && <HumanApprovalPanel taskId={taskId} />}

        <div className="live-monitor__layout">
          <div className="live-monitor__groups">
            {GROUPS.map((group) => (
              <section key={group.label} className="live-monitor__group">
                <h2 className="live-monitor__group-title">{group.label}</h2>
                <div className="live-monitor__grid">
                  {group.agents.map((agentName) => <AgentPanel key={agentName} run={mergedRuns[agentName] ?? placeholderRun(agentName)} />)}
                </div>
              </section>
            ))}
          </div>
          <div className="live-monitor__log"><LogStream lines={lines} /></div>
        </div>
      </main>
    </div>
  );
}
