// frontend/src/api/index.ts
import { api } from "./client";
import type { AgentRun, CodeOutputDetail, CodeOutputSummary, FileTreeNode, LogEntry, Priority, Project, RiskScore, Task, TaskListResponse } from "../types";

export interface CreateTaskPayload { title: string; description?: string; language?: string; framework?: string; project_id?: string; priority?: Priority; max_exec_minutes?: number; git_integration?: boolean; }
export interface TaskListParams { status?: string; priority?: string; language?: string; project_id?: string; search?: string; page?: number; page_size?: number; sort_by?: string; sort_desc?: boolean; }
function toQuery(params: object): string { const usable = Object.entries(params).filter(([, v]) => v !== undefined && v !== ""); if (usable.length === 0) return ""; return "?" + usable.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&"); }

export const tasksApi = {
  create: (payload: CreateTaskPayload) => api.post<Task>("/tasks", payload),
  get: (taskId: string) => api.get<Task>(`/tasks/${taskId}`),
  list: (params: TaskListParams = {}) => api.get<TaskListResponse>(`/tasks${toQuery(params)}`),
  update: (taskId: string, patch: Partial<CreateTaskPayload & { status: string }>) => api.patch<Task>(`/tasks/${taskId}`, patch),
  remove: (taskId: string) => api.delete<void>(`/tasks/${taskId}`),
};

export const agentsApi = {
  runs: (taskId: string) => api.get<AgentRun[]>(`/agents/runs/${taskId}`),
  pendingPlan: (taskId: string) => api.get<{ pending: boolean; plan: Record<string, unknown> | null }>(`/agents/${taskId}/pending-plan`),
  approvePlan: (taskId: string) => api.post<void>(`/agents/${taskId}/approve`),
  rejectPlan: (taskId: string, reason?: string) => api.post<void>(`/agents/${taskId}/reject`, { reason }),
  editPlan: (taskId: string, plan: Record<string, unknown>) => api.post<void>(`/agents/${taskId}/edit-plan`, { plan }),
  addRole: (taskId: string, roleName: string, reason?: string) => api.post<AgentRun>(`/agents/${taskId}/add-role`, { role_name: roleName, reason }),
  riskScore: (taskId: string) => api.get<RiskScore>(`/agents/${taskId}/risk-score`),
  groundingReport: (taskId: string) => api.get<{ grounded: boolean; unsupported_claims: unknown[] }>(`/agents/${taskId}/grounding-report`),
};

export const outputsApi = {
  list: (taskId: string) => api.get<CodeOutputSummary[]>(`/tasks/${taskId}/outputs`),
  tree: (taskId: string) => api.get<FileTreeNode>(`/tasks/${taskId}/outputs/tree`),
  file: (taskId: string, outputId: string) => api.get<CodeOutputDetail>(`/tasks/${taskId}/outputs/${outputId}`),
  downloadZipUrl: (taskId: string) => `${import.meta.env.VITE_API_URL ?? "http://localhost:8000"}/api/v1/tasks/${taskId}/outputs/download/zip`,
};

export const logsApi = {
  list: (taskId: string, params: Record<string, unknown> = {}) => api.get<{ items: LogEntry[]; total: number; page: number; page_size: number }>(`/tasks/${taskId}/logs${toQuery(params)}`),
  resolve: (taskId: string, logId: number, note?: string) => api.patch<LogEntry>(`/tasks/${taskId}/logs/${logId}/resolve`, { note }),
  analytics: (taskId: string) => api.get<{ total: number; unresolved: number; by_severity: Record<string, number>; by_agent: Record<string, number> }>(`/tasks/${taskId}/logs/analytics`,),
};

export const projectsApi = { list: () => api.get<Project[]>("/projects") };
export { api } from "./client";
