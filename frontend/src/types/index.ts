// frontend/src/types/index.ts
// Mirrors the Pydantic response models in backend/routers/*.py. Kept as
// one file since most pages need a handful of overlapping shapes rather
// than one type each — split this up if any single domain outgrows it.

export type TaskStatus = "pending" | "running" | "completed" | "failed";
export type Priority = "low" | "medium" | "high";

export interface Task {
  id: string;
  title: string;
  description: string | null;
  language: string | null;
  framework: string | null;
  status: TaskStatus;
  priority: Priority;
  replan_count: number;
  coder_retries: number;
  safety_issues_found: number;
  human_interventions: number;
  review_score: number | null;
}

export interface TaskListResponse {
  items: Task[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Order matters here — it's the pipeline order from workflow/workflow.py,
// and LiveMonitor renders panels in this sequence.
export const AGENT_PIPELINE = [
  "GUARDRAIL",
  "PLANNER",
  "GROUNDING",
  "HUMAN",
  "IDENTITY_BROKER",
  "CODER",
  "TESTER",
  "SECURITY",
  "REVIEWER",
  "CONTEXT_CURATOR",
] as const;

export type AgentName = (typeof AGENT_PIPELINE)[number] | string;

export type AgentRunStatus = "pending" | "queued" | "running" | "completed" | "failed";

export interface AgentRun {
  id: string;
  agent_name: AgentName;
  agent_color: string | null;
  status: AgentRunStatus;
  current_subtask: string | null;
  step_current: number;
  step_total: number;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
}

export interface LogEntry {
  id: number;
  agent_name: string;
  log_level: string;
  prefix_icon: string | null;
  message: string;
  agent_color: string | null;
  severity: "info" | "critical";
  error_code: string | null;
  is_resolved: boolean;
  resolved_at: string | null;
  created_at: string;
}

export interface CodeOutputSummary {
  id: string;
  file_path: string;
  file_name: string;
  file_type: string | null;
  language: string | null;
  line_count: number;
  is_new_file: boolean;
  is_test_file: boolean;
  is_doc_file: boolean;
}

export interface CodeOutputDetail extends CodeOutputSummary {
  content: string;
  annotations: unknown[];
}

export interface FileTreeNode {
  name: string;
  type: "file" | "folder";
  id?: string;
  file_type?: string | null;
  language?: string | null;
  line_count?: number;
  children?: FileTreeNode[];
}

export interface RiskScore {
  running_score: number;
  last_verdict: "allow" | "flag" | "block";
  updated_at: string;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  status: "active" | "completed" | "archived";
}
