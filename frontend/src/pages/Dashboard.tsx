// frontend/src/pages/Dashboard.tsx
// Landing page after login — recent tasks plus a quick glance at whatever
// is currently running. The pipeline strip on each running task's row
// mirrors the same 10-agent order Live Monitor uses, just compressed.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sidebar, StatusPill } from "../components";
import { tasksApi } from "../api";
import { AGENT_PIPELINE, type Task } from "../types";
import "./Dashboard.css";

export default function Dashboard() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    tasksApi
      .list({ page_size: 10, sort_by: "created_at", sort_desc: true })
      .then((res) => {
        if (!cancelled) setTasks(res.items);
      })
      .catch(() => {
        if (!cancelled) setLoadError("Couldn't load your tasks — try refreshing.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const runningCount = tasks.filter((t) => t.status === "running").length;
  const completedCount = tasks.filter((t) => t.status === "completed").length;

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <div className="page-header">
          <div>
            <h1>Dashboard</h1>
            <p className="page-header__meta">
              {runningCount} running · {completedCount} completed recently
            </p>
          </div>
          <Link to="/tasks/new" className="btn btn--fill">
            New Task
          </Link>
        </div>

        {isLoading && <p className="dashboard__status-text">Loading tasks…</p>}
        {loadError && <p className="dashboard__status-text">{loadError}</p>}

        {!isLoading && !loadError && tasks.length === 0 && (
          <div className="empty-state">
            <h3>No tasks yet</h3>
            <p>Start one and the Planner will break it down for you.</p>
            <Link to="/tasks/new" className="btn btn--fill">
              Create your first task
            </Link>
          </div>
        )}

        <div className="dashboard__list">
          {tasks.map((task) => (
            <Link key={task.id} to={`/monitor?task=${task.id}`} className="dashboard__row">
              <div className="dashboard__row-main">
                <span className="dashboard__row-title">{task.title}</span>
                <span className="dashboard__row-sub">
                  {task.language ?? "unspecified"} · {task.priority} priority
                </span>
              </div>

              <div className="dashboard__pipeline" aria-hidden="true">
                {AGENT_PIPELINE.map((agent) => (
                  <span key={agent} className="dashboard__pipeline-dot" title={agent} />
                ))}
              </div>

              <div className="dashboard__row-meta">
                {task.review_score != null && <span className="mono">{task.review_score.toFixed(1)}/10</span>}
                <StatusPill status={task.status} />
              </div>
            </Link>
          ))}
        </div>
      </main>
    </div>
  );
}
