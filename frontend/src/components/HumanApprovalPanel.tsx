import { useEffect, useState } from "react";
import { agentsApi } from "../api";
import "./HumanApprovalPanel.css";

interface HumanApprovalPanelProps {
  taskId: string;
}

interface PendingPlan {
  task_summary?: string;
  estimated_minutes?: number;
  complexity?: string;
  subtasks?: Array<{
    id?: number;
    title?: string;
    file?: string;
    description?: string;
    agent?: string;
  }>;
}

export function HumanApprovalPanel({ taskId }: HumanApprovalPanelProps) {
  const [plan, setPlan] = useState<PendingPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [jsonText, setJsonText] = useState("");

  const load = async () => {
    try {
      const response = await agentsApi.pendingPlan(taskId);
      if (response.pending && response.plan) {
        setPlan(response.plan as PendingPlan);
        setJsonText(JSON.stringify(response.plan, null, 2));
      } else {
        setPlan(null);
      }
      setError(null);
    } catch {
      setError("Unable to load the pending plan.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 2000);
    return () => window.clearInterval(timer);
  }, [taskId]);

  if (loading && !plan) return null;
  if (!plan) return null;

  const approve = async () => {
    setBusy(true);
    setError(null);
    try {
      await agentsApi.approvePlan(taskId);
      setPlan(null);
    } catch {
      setError("Approval failed. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    const reason = window.prompt("Why do you want to reject this plan?", "Please revise the plan.");
    if (reason === null) return;
    setBusy(true);
    setError(null);
    try {
      await agentsApi.rejectPlan(taskId, reason);
      setPlan(null);
    } catch {
      setError("Rejection failed. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const saveEdit = async () => {
    try {
      const edited = JSON.parse(jsonText) as Record<string, unknown>;
      setBusy(true);
      setError(null);
      await agentsApi.editPlan(taskId, edited);
      setPlan(null);
      setEditing(false);
    } catch (err) {
      setError(err instanceof SyntaxError ? "The edited plan is not valid JSON." : "Plan update failed. Please try again.");
      setBusy(false);
    }
  };

  return (
    <section className="human-approval">
      <div className="human-approval__header">
        <div>
          <div className="human-approval__eyebrow">HUMAN APPROVAL REQUIRED</div>
          <h2>Review the agent plan</h2>
          <p>The workflow is paused. Approve the plan to let the Identity Broker and Coder continue.</p>
        </div>
        <span className="human-approval__status">WAITING</span>
      </div>

      <div className="human-approval__summary">
        <div>
          <span>Task</span>
          <strong>{plan.task_summary || "Implementation plan"}</strong>
        </div>
        <div>
          <span>Estimated</span>
          <strong>{plan.estimated_minutes ?? "—"} min</strong>
        </div>
        <div>
          <span>Complexity</span>
          <strong>{plan.complexity || "—"}</strong>
        </div>
      </div>

      {editing ? (
        <textarea className="human-approval__editor" value={jsonText} onChange={(e) => setJsonText(e.target.value)} />
      ) : (
        <div className="human-approval__steps">
          {(plan.subtasks || []).map((subtask, index) => (
            <div className="human-approval__step" key={`${subtask.id ?? index}-${subtask.title}`}>
              <span className="human-approval__number">{subtask.id ?? index + 1}</span>
              <div>
                <strong>{subtask.title || "Untitled subtask"}</strong>
                <p>{subtask.description || "No description provided."}</p>
                {subtask.file && <code>{subtask.file}</code>}
              </div>
            </div>
          ))}
        </div>
      )}

      {error && <div className="human-approval__error">{error}</div>}

      <div className="human-approval__actions">
        {editing ? (
          <>
            <button type="button" className="human-approval__button" onClick={() => setEditing(false)} disabled={busy}>Cancel</button>
            <button type="button" className="human-approval__button human-approval__button--approve" onClick={() => void saveEdit()} disabled={busy}>Save & Approve</button>
          </>
        ) : (
          <>
            <button type="button" className="human-approval__button human-approval__button--reject" onClick={() => void reject()} disabled={busy}>Reject</button>
            <button type="button" className="human-approval__button" onClick={() => setEditing(true)} disabled={busy}>Edit Plan</button>
            <button type="button" className="human-approval__button human-approval__button--approve" onClick={() => void approve()} disabled={busy}>✓ Approve Plan</button>
          </>
        )}
      </div>
    </section>
  );
}
