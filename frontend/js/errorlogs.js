// js/errorlogs.js

let currentTaskId = null;

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function loadLogs() {
  if (!currentTaskId) return;
  const statusText = document.getElementById("status-text");
  const list = document.getElementById("log-list");

  const params = new URLSearchParams({ page_size: "50" });
  const severity = document.getElementById("severity-filter").value;
  const agent = document.getElementById("agent-filter").value;
  const unresolvedOnly = document.getElementById("unresolved-only").checked;
  if (severity) params.set("severity", severity);
  if (agent) params.set("agent", agent);
  if (unresolvedOnly) params.set("resolved", "false");

  try {
    const res = await api.get(`/tasks/${currentTaskId}/logs?${params.toString()}`);
    statusText.style.display = "none";
    document.getElementById("filters").style.display = "flex";

    if (res.items.length === 0) {
      list.innerHTML = `<div class="empty-state"><h3>No log entries match</h3></div>`;
      return;
    }

    list.innerHTML = res.items
      .map(
        (log) => `
      <div class="errorlogs__row errorlogs__row--${log.severity}" data-log-id="${log.id}">
        <span class="errorlogs__icon">${log.prefix_icon || ""}</span>
        <span class="errorlogs__agent">${log.agent_name}</span>
        <span class="errorlogs__message">${escapeHtml(log.message)}</span>
        <span class="errorlogs__time">${new Date(log.created_at).toLocaleTimeString()}</span>
        ${
          log.is_resolved
            ? `<span class="errorlogs__resolved">✓ resolved</span>`
            : `<button type="button" class="errorlogs__resolve-btn" data-log-id="${log.id}">Resolve</button>`
        }
      </div>`,
      )
      .join("");

    list.querySelectorAll(".errorlogs__resolve-btn").forEach((btn) => {
      btn.addEventListener("click", () => resolveLog(btn.dataset.logId));
    });
  } catch (err) {
    statusText.style.display = "block";
    statusText.textContent = err instanceof Error ? err.message : "Couldn't load logs for that task.";
  }
}

async function resolveLog(logId) {
  try {
    await api.patch(`/tasks/${currentTaskId}/logs/${logId}/resolve`, {});
    loadLogs();
  } catch (err) {
    alert(err instanceof Error ? err.message : "Couldn't resolve that entry.");
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = await requireAuth();
  if (!token) return;
  renderSidebar("errorlogs.html");

  const fromUrl = new URLSearchParams(window.location.search).get("task");
  if (fromUrl) {
    document.getElementById("task-id-input").value = fromUrl;
    currentTaskId = fromUrl;
    loadLogs();
  }

  document.getElementById("load-btn").addEventListener("click", () => {
    currentTaskId = document.getElementById("task-id-input").value.trim();
    if (currentTaskId) loadLogs();
  });
  document.getElementById("severity-filter").addEventListener("change", loadLogs);
  document.getElementById("agent-filter").addEventListener("change", loadLogs);
  document.getElementById("unresolved-only").addEventListener("change", loadLogs);
});
