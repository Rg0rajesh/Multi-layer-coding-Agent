// js/dashboard.js

const STATUS_LABELS = {
  pending: "Pending",
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

function statusPill(status) {
  const label = STATUS_LABELS[status] || status;
  return `<span class="status-pill status-pill--${status}">${label}</span>`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderTasks(tasks) {
  const list = document.getElementById("task-list");
  const empty = document.getElementById("empty-state");
  const running = tasks.filter((t) => t.status === "running").length;
  const completed = tasks.filter((t) => t.status === "completed").length;

  document.getElementById("task-summary").textContent =
    `${running} running · ${completed} completed recently`;

  if (tasks.length === 0) {
    empty.style.display = "";
    list.innerHTML = "";
    return;
  }

  empty.style.display = "none";
  list.innerHTML = tasks
    .map(
      (task) => `
    <a href="livemonitor.html?task=${task.id}" class="dashboard__row">
      <div class="dashboard__row-main">
        <span class="dashboard__row-title">${escapeHtml(task.title)}</span>
        <span class="dashboard__row-sub">${escapeHtml(task.language || "unspecified")} · ${escapeHtml(task.priority)} priority</span>
      </div>
      <div class="dashboard__row-meta">
        ${task.review_score != null ? `<span class="mono">${task.review_score.toFixed(1)}/10</span>` : ""}
        ${statusPill(task.status)}
      </div>
    </a>`,
    )
    .join("");
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = await requireAuth();
  if (!token) return;
  renderSidebar("dashboard.html");

  try {
    const res = await api.get("/tasks?page_size=10&sort_by=created_at&sort_desc=true");
    renderTasks(res.items);
  } catch (err) {
    document.getElementById("status-text").textContent =
      err instanceof Error ? `Couldn't load your tasks — ${err.message}` : "Couldn't load your tasks.";
  }
});
