// js/livemonitor.js — port of useWebSocket.ts + useAgentStream.ts

const WS_BASE_URL = "ws://localhost:8000";
const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_RECONNECT_DELAY_MS = 1000;
const MAX_LOG_LINES = 500;

// Mirrors backend/services/log_service.py::AGENT_COLORS
const AGENT_COLORS = {
  PLANNER: "#E8FF47",
  CODER: "#00C896",
  TESTER: "#FF6B35",
  REVIEWER: "#FF3C3C",
  SECURITY: "#FF3C3C",
  HUMAN: "#FFFFFF",
  SYSTEM: "#888888",
  GUARDRAIL: "#FF3C3C",
  IDENTITY_BROKER: "#E8FF47",
  GROUNDING: "#00C896",
  CONTEXT_CURATOR: "#888888",
};

const AGENT_ORDER = [
  "GUARDRAIL", "PLANNER", "GROUNDING", "HUMAN", "IDENTITY_BROKER",
  "CODER", "TESTER", "SECURITY", "REVIEWER", "CONTEXT_CURATOR",
];

let socket = null;
let attempts = 0;
let reconnectTimer = null;
let closedByUs = false;
let lines = [];
const agentStatuses = {};

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function setWsIndicator(status) {
  const el = document.getElementById("ws-indicator");
  const labels = { connecting: "○ connecting", open: "● live", closed: "○ disconnected", error: "✗ error" };
  el.textContent = labels[status] || status;
  el.className = `ws-indicator ws-indicator--${status}`;
}

function renderAgentPanels() {
  const grid = document.getElementById("agent-panel-grid");
  grid.innerHTML = AGENT_ORDER.map((agent) => {
    const s = agentStatuses[agent];
    const color = AGENT_COLORS[agent] || "#FFFFFF";
    return `
      <div class="agent-panel" style="--agent-color:${color}">
        <span class="agent-panel__name">${agent}</span>
        <span class="agent-panel__status">${s ? s.lastLevel : "idle"}</span>
      </div>`;
  }).join("");
}

function renderLogStream() {
  const stream = document.getElementById("log-stream");
  stream.innerHTML = lines
    .map(
      (line) => `
    <div class="log-stream__line" style="--agent-color:${line.color}">
      <span class="log-stream__agent">${line.agent}</span>
      <span class="log-stream__icon">${line.icon}</span>
      <span class="log-stream__message">${escapeHtml(line.message)}</span>
    </div>`,
    )
    .join("");
  stream.scrollTop = stream.scrollHeight;
}

function handleMessage(raw) {
  agentStatuses[raw.agent] = {
    agent: raw.agent,
    lastSeenAt: raw.timestamp,
    lastLevel: raw.type === "log" ? raw.level : (agentStatuses[raw.agent]?.lastLevel ?? "INFO"),
  };
  renderAgentPanels();

  if (raw.type !== "log") return;

  lines.push({
    id: `${raw.timestamp}-${lines.length}`,
    agent: raw.agent,
    level: raw.level,
    icon: raw.icon,
    message: raw.message,
    timestamp: raw.timestamp,
    color: AGENT_COLORS[raw.agent] || "#FFFFFF",
  });
  if (lines.length > MAX_LOG_LINES) lines = lines.slice(lines.length - MAX_LOG_LINES);
  renderLogStream();
}

function connectWebSocket(taskId) {
  setWsIndicator("connecting");
  socket = new WebSocket(`${WS_BASE_URL}/ws/task/${taskId}`);

  socket.onopen = () => {
    attempts = 0;
    setWsIndicator("open");
  };

  socket.onmessage = (event) => {
    try {
      handleMessage(JSON.parse(event.data));
    } catch {
      console.warn("Couldn't parse WS message:", event.data);
    }
  };

  socket.onerror = () => setWsIndicator("error");

  socket.onclose = () => {
    setWsIndicator("closed");
    if (closedByUs) return;
    if (attempts < MAX_RECONNECT_ATTEMPTS) {
      const delay = BASE_RECONNECT_DELAY_MS * 2 ** attempts;
      attempts += 1;
      reconnectTimer = setTimeout(() => connectWebSocket(taskId), delay);
    }
  };
}

function getTaskIdFromUrl() {
  return new URLSearchParams(window.location.search).get("task");
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = await requireAuth();
  if (!token) return;
  renderSidebar("livemonitor.html");
  renderAgentPanels();

  const taskId = getTaskIdFromUrl();
  const statusText = document.getElementById("status-text");
  if (!taskId) {
    statusText.style.display = "block";
    statusText.textContent = "No task selected — open a task from the Dashboard or History page.";
    document.getElementById("ws-indicator").style.display = "none";
    return;
  }

  try {
    const task = await api.get(`/tasks/${taskId}`);
    document.getElementById("task-title").textContent = task.title;
  } catch (err) {
    statusText.style.display = "block";
    statusText.textContent = err instanceof Error ? err.message : "Couldn't load this task.";
  }

  connectWebSocket(taskId);

  window.addEventListener("beforeunload", () => {
    closedByUs = true;
    clearTimeout(reconnectTimer);
    socket?.close();
  });
});
