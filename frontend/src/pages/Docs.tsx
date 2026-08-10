// frontend/src/pages/Docs.tsx
// Spec page 10 calls for a full nav-tree + Markdown renderer + sticky TOC.
// Pulling in a Markdown library for static reference content this small
// isn't worth the bundle weight yet — this ships the structure with the
// actual content hardcoded, and swaps to a real Markdown source (e.g. a
// docs/ folder fetched at build time) once there's more than one page of it.
import { useState } from "react";
import { Sidebar } from "../components";
import "./Docs.css";

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "agents", label: "Agent Pipeline" },
  { id: "memory", label: "Memory Tiers" },
  { id: "api", label: "API Reference" },
];

export default function Docs() {
  const [active, setActive] = useState("overview");

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main docs">
        <nav className="docs__nav">
          {SECTIONS.map((section) => (
            <button
              key={section.id}
              className={`docs__nav-item${active === section.id ? " is-active" : ""}`}
              onClick={() => setActive(section.id)}
            >
              {section.label}
            </button>
          ))}
        </nav>

        <article className="docs__content">
          {active === "overview" && (
            <>
              <h1>AGENT X</h1>
              <p>
                A 10-agent coding pipeline — Guardrail, Planner, Grounding, Human, Identity Broker, Coder,
                Tester, Security, Reviewer, and Context Curator — running over LangGraph and AutoGen, with a
                3-tier memory system underneath.
              </p>
            </>
          )}
          {active === "agents" && (
            <>
              <h2>Agent Pipeline</h2>
              <p>
                Guardrail screens every incoming task before Planner sees it. Grounding checks the plan
                against real repo state. Identity Broker issues a scoped, short-lived credential once a
                human approves the plan — Coder and Tester run under it, never under a full account
                credential.
              </p>
            </>
          )}
          {active === "memory" && (
            <>
              <h2>Memory Tiers</h2>
              <p>
                Task memory resets per run. Project memory only accepts writes through Context Curator —
                raw session logs never land there directly. Developer memory persists per user across every
                project.
              </p>
            </>
          )}
          {active === "api" && (
            <>
              <h2>API Reference</h2>
              <p className="mono">GET /api/v1/agents/:task_id/risk-score</p>
              <p className="mono">GET /api/v1/agents/:task_id/grounding-report</p>
              <p className="mono">GET /api/v1/agents/:task_id/curated-memory</p>
            </>
          )}
        </article>
      </main>
    </div>
  );
}
