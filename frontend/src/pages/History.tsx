// frontend/src/pages/History.tsx
import { Fragment, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Sidebar, StatusPill } from "../components";
import { tasksApi } from "../api";
import type { Task, TaskStatus } from "../types";
import "./History.css";

const STATUS_FILTERS: { label: string; value: TaskStatus | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Running", value: "running" },
  { label: "Completed", value: "completed" },
  { label: "Failed", value: "failed" },
];

export default function History() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await tasksApi.list({
        page,
        page_size: 20,
        status: statusFilter === "all" ? undefined : statusFilter,
        search: search || undefined,
        sort_by: "created_at",
        sort_desc: true,
      });

      setTasks(res.items ?? []);
      setTotal(res.total ?? 0);
    } catch (err) {
      console.error("Failed to load task history", err);
      setError(err instanceof Error ? err.message : "Unable to load task history");
      setTasks([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, search]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      if (!cancelled) await loadHistory();
    })();

    return () => {
      cancelled = true;
    };
  }, [loadHistory]);

  const totalPages = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <div className="page-header">
          <div>
            <h1>History</h1>
            <p className="page-subtitle">Your previous AGENTX tasks</p>
          </div>
          <button type="button" className="btn" onClick={loadHistory} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>

        <div className="history__toolbar">
          <input
            className="history__search"
            placeholder="Search tasks…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
          <div className="history__filters">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                type="button"
                className={`history__filter${statusFilter === f.value ? " is-active" : ""}`}
                onClick={() => {
                  setStatusFilter(f.value);
                  setPage(1);
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="history__error" role="alert">
            <strong>Could not load history.</strong>
            <span>{error}</span>
            <button type="button" className="btn" onClick={loadHistory}>
              Try again
            </button>
          </div>
        )}

        {!error && loading && (
          <div className="empty-state">
            <h3>Loading history…</h3>
            <p>Fetching your previous tasks.</p>
          </div>
        )}

        {!error && !loading && tasks.length === 0 && (
          <div className="empty-state">
            <h3>No tasks yet</h3>
            <p>Your completed and running tasks will appear here automatically.</p>
          </div>
        )}

        {!error && !loading && tasks.length > 0 && (
          <>
            <table className="history__table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Stack</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {tasks.map((task) => (
                  <Fragment key={task.id}>
                    <tr
                      className="history__row"
                      onClick={() => setExpandedId(expandedId === task.id ? null : task.id)}
                    >
                      <td>{task.title}</td>
                      <td className="mono">{task.language ?? "—"}</td>
                      <td><StatusPill status={task.status} /></td>
                      <td className="mono">
                        {task.review_score != null ? task.review_score.toFixed(1) : "—"}
                      </td>
                      <td>
                        <Link
                          to={`/monitor?task=${task.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="history__link"
                        >
                          View →
                        </Link>
                      </td>
                    </tr>
                    {expandedId === task.id && (
                      <tr className="history__detail-row">
                        <td colSpan={5}>
                          <div className="history__detail">
                            <span>{task.replan_count} re-plan(s)</span>
                            <span>{task.coder_retries} coder retr(y/ies)</span>
                            <span>{task.safety_issues_found} safety finding(s)</span>
                            <span>{task.human_interventions} human intervention(s)</span>
                            <Link to={`/output?task=${task.id}`} className="history__link">
                              Open code output →
                            </Link>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>

            <div className="history__pagination">
              <button className="btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                Previous
              </button>
              <span className="mono">Page {page} of {totalPages}</span>
              <button className="btn" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                Next
              </button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
