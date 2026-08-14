import { useEffect, useState } from "react";
import { outputsApi } from "../api";
import type { CodeOutputDetail, CodeOutputSummary } from "../types";
import "./LiveCodePanel.css";

export default function LiveCodePanel({ taskId }: { taskId: string }) {
  const [files, setFiles] = useState<CodeOutputSummary[]>([]);
  const [active, setActive] = useState<CodeOutputDetail | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const next = await outputsApi.list(taskId);
        if (cancelled) return;
        setFiles(next);
        if (!active && next[0]) {
          const detail = await outputsApi.file(taskId, next[0].id);
          if (!cancelled) setActive(detail);
        } else if (active) {
          const current = next.find((file) => file.id === active.id);
          if (current) {
            const detail = await outputsApi.file(taskId, current.id);
            if (!cancelled) setActive(detail);
          }
        }
      } catch {
        // The task may not have produced a file yet.
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 1200);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [taskId, active?.id]);

  return (
    <section className="live-code-panel card">
      <div className="live-code-panel__header">
        <div><strong>Live Code</strong><span>{files.length} file(s)</span></div>
        <span className="live-code-panel__status">LIVE</span>
      </div>
      <div className="live-code-panel__body">
        <aside className="live-code-panel__files">
          {files.map((file) => (
            <button key={file.id} type="button" className={active?.id === file.id ? "is-active" : ""} onClick={async () => setActive(await outputsApi.file(taskId, file.id))}>
              <span>{file.file_name}</span><small>{file.line_count} lines</small>
            </button>
          ))}
          {!files.length && <p>Waiting for Coder to write a file…</p>}
        </aside>
        <div className="live-code-panel__editor">
          {active ? <><div className="live-code-panel__path">{active.file_path}</div><pre><code>{active.content}</code></pre></> : <p>Code will appear here as the agent writes it.</p>}
        </div>
      </div>
    </section>
  );
}
