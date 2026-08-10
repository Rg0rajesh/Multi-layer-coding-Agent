// frontend/src/pages/ErrorLogs.tsx
// Spec page 16. Reuses the same task-scoped log endpoint History and
// Dashboard use — this page just defaults the filter to critical/error
// severity and adds the resolve action routers/logs.py exposes.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Sidebar } from "../components";
import { logsApi } from "../api";
import type { LogEntry } from "../types";
import "./ErrorLogs.css";

export default function ErrorLogs() {
  const [params] = useSearchParams();
  const taskId = params.get("task");

  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [selected, setSelected] = useState<LogEntry | null>(null);

  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;

    logsApi
      .list(taskId, { severity: "critical", agent: agentFilter === "all" ? undefined : agentFilter, page_size: 100 })
      .then((res) => !cancelled && setLogs(res.items))
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [taskId, agentFilter]);

  async function resolve(log: LogEntry) {
    if (!taskId) return;
    try {
      const updated = await logsApi.resolve(taskId, log.id);
      setLogs((prev) => prev.map((l) => (l.id === log.id ? updated : l)));
    } catch {
      // leave it unresolved in the UI — the retry is just clicking again
    }
  }

  const agents = Array.from(new Set(logs.map((l) => l.agent_name)));

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <div className="page-header">
          <h1>Error Logs</h1>
        </div>

        {!taskId ? (
          <div className="empty-state">
            <h3>No task selected</h3>
            <p>Open a task to see its error console.</p>
          </div>
        ) : (
          <div className="error-logs__layout">
            <section>
              <div className="error-logs__toolbar">
                <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)}>
                  <option value="all">All agents</option>
                  {agents.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </div>

              <table className="error-logs__table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Agent</th>
                    <th>Message</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr
                      key={log.id}
                      className={`error-logs__row${log.is_resolved ? " is-resolved" : ""}`}
                      onClick={() => setSelected(log)}
                    >
                      <td className="mono">{new Date(log.created_at).toLocaleTimeString()}</td>
                      <td>{log.agent_name}</td>
                      <td className="error-logs__message">{log.message}</td>
                      <td>{log.is_resolved ? "Resolved" : "Open"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {logs.length === 0 && (
                <div className="empty-state">
                  <h3>No critical errors</h3>
                  <p>Nothing's blocking this task right now.</p>
                </div>
              )}
            </section>

            <aside className="card error-logs__detail">
              {selected ? (
                <>
                  <h3>{selected.agent_name}</h3>
                  <p className="mono error-logs__detail-code">{selected.error_code ?? "no error code"}</p>
                  <p>{selected.message}</p>
                  {!selected.is_resolved && (
                    <button className="btn btn--fill" onClick={() => resolve(selected)}>
                      Mark resolved
                    </button>
                  )}
                </>
              ) : (
                <p className="code-output__hint">Select a row to see the full detail.</p>
              )}
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}
