// frontend/src/pages/CodeOutput.tsx
// Spec page 06: file tree on the left, read-only editor center, agent
// annotations + Code/Tests/Docs/Review tabs on the right. Keeps it to a
// plain <pre> instead of a syntax-highlighting library — the spec calls
// for monochrome weight-based highlighting anyway, which a full
// highlighter would fight against more than help with.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Sidebar } from "../components";
import { outputsApi } from "../api";
import type { CodeOutputDetail, CodeOutputSummary, FileTreeNode } from "../types";
import "./CodeOutput.css";

function FileTree({ node, onSelect, depth = 0 }: { node: FileTreeNode; onSelect: (id: string) => void; depth?: number }) {
  if (node.type === "file") {
    return (
      <button
        type="button"
        className="code-output__tree-file"
        style={{ paddingLeft: 12 + depth * 14 }}
        onClick={() => node.id && onSelect(node.id)}
      >
        {node.name}
      </button>
    );
  }

  return (
    <div>
      {node.name !== "root" && (
        <div className="code-output__tree-folder" style={{ paddingLeft: 12 + depth * 14 }}>
          {node.name}
        </div>
      )}
      {node.children?.map((child) => (
        <FileTree key={child.name} node={child} onSelect={onSelect} depth={node.name === "root" ? depth : depth + 1} />
      ))}
    </div>
  );
}

export default function CodeOutput() {
  const [params] = useSearchParams();
  const taskId = params.get("task");

  const [tree, setTree] = useState<FileTreeNode | null>(null);
  const [files, setFiles] = useState<CodeOutputSummary[]>([]);
  const [activeFile, setActiveFile] = useState<CodeOutputDetail | null>(null);
  const [activeTab, setActiveTab] = useState<"code" | "tests" | "docs" | "review">("code");

  useEffect(() => {
    if (!taskId) return;
    outputsApi.tree(taskId).then(setTree).catch(() => {});
    outputsApi.list(taskId).then(setFiles).catch(() => {});
  }, [taskId]);

  async function selectFile(outputId: string) {
    if (!taskId) return;
    try {
      const detail = await outputsApi.file(taskId, outputId);
      setActiveFile(detail);
      setActiveTab("code");
    } catch {
      // stays on the previously selected file — nothing to recover into
    }
  }

  const lineCount = activeFile?.content.split("\n").length ?? 0;
  const totalLines = files.reduce((sum, f) => sum + f.line_count, 0);
  const testFileCount = files.filter((f) => f.is_test_file).length;

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main code-output">
        <div className="page-header">
          <h1>Code Output</h1>
          {taskId && (
            <a className="btn" href={outputsApi.downloadZipUrl(taskId)}>
              Download ZIP
            </a>
          )}
        </div>

        {!taskId ? (
          <div className="empty-state">
            <h3>No task selected</h3>
            <p>Open a completed task to browse its generated files.</p>
          </div>
        ) : (
          <div className="code-output__layout">
            <aside className="code-output__tree card">
              {tree ? <FileTree node={tree} onSelect={selectFile} /> : <p className="code-output__hint">No files yet.</p>}
            </aside>

            <section className="code-output__editor card">
              {activeFile ? (
                <>
                  <div className="code-output__breadcrumb mono">{activeFile.file_path}</div>
                  <pre className="code-output__pre">
                    <code>{activeFile.content}</code>
                  </pre>
                </>
              ) : (
                <p className="code-output__hint">Select a file from the tree to view it.</p>
              )}
            </section>

            <aside className="code-output__side card">
              <div className="code-output__tabs">
                {(["code", "tests", "docs", "review"] as const).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    className={`code-output__tab${activeTab === tab ? " is-active" : ""}`}
                    onClick={() => setActiveTab(tab)}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              <div className="code-output__stats">
                <div>
                  <span className="code-output__stat-value">{totalLines}</span>
                  <span className="code-output__stat-label">Lines of Code</span>
                </div>
                <div>
                  <span className="code-output__stat-value">{files.length}</span>
                  <span className="code-output__stat-label">Files</span>
                </div>
                <div>
                  <span className="code-output__stat-value">{testFileCount}</span>
                  <span className="code-output__stat-label">Test Files</span>
                </div>
                <div>
                  <span className="code-output__stat-value">{lineCount || "—"}</span>
                  <span className="code-output__stat-label">Selected File Lines</span>
                </div>
              </div>
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}
