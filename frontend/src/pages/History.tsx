// frontend/src/pages/History.tsx
// Spec page 12: dense table, not a card grid. Row click expands an inline
// detail row instead of navigating away — sorting/filtering state stays
// intact that way, which a full navigation would lose.
import { Fragment, useEffect, useState } from "react";
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

  useEffect(() => {
    let cancelled = false;

    tasksApi
      .list({
        page,
        page_size: 20,
        status: statusFilter === "all" ? undefined : statusFilter,
        search: search || undefined,
        sort_by: "created_at",
        sort_desc: true,
      })
      .then((res) => {
        if (cancelled) return;
        setTasks(res.items);
        setTotal(res.total);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [page, statusFilter, search]);

  const totalPages = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <div className="page-header">
          <h1>History</h1>
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
                  key={task.id}
                  className="history__row"
                  onClick={() => setExpandedId(expandedId === task.id ? null : task.id)}
                >
                  <td>{task.title}</td>
                  <td className="mono">{task.language ?? "—"}</td>
                  <td>
                    <StatusPill status={task.status} />
                  </td>
                  <td className="mono">{task.review_score != null ? task.review_score.toFixed(1) : "—"}</td>
                  <td>
                    <Link to={`/monitor?task=${task.id}`} onClick={(e) => e.stopPropagation()} className="history__link">
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

        {tasks.length === 0 && (
          <div className="empty-state">
            <h3>No matching tasks</h3>
            <p>Try a different search or filter.</p>
          </div>
        )}

        <div className="history__pagination">
          <button className="btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </button>
          <span className="mono">
            Page {page} of {totalPages}
          </span>
          <button className="btn" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Next
          </button>
        </div>
      </main>
    </div>
  );
}
