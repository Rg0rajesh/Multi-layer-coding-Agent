// js/history.js

const STATUS_LABELS = {
  pending: "Pending", queued: "Queued", running: "Running",
  completed: "Completed", failed: "Failed",
};

function statusPill(status) {
  return `<span class="status-pill status-pill--${status}">${STATUS_LABELS[status] || status}</span>`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

let page = 1;
const pageSize = 15;
let debounceTimer = null;

async function loadHistory() {
  const statusText = document.getElementById("status-text");
  const search = document.getElementById("search").value.trim();
  const status = document.getElementById("status-filter").value;

  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    sort_by: "created_at",
    sort_desc: "true",
  });
  if (search) params.set("search", search);
  if (status) params.set("status", status);

  try {
    const res = await api.get(`/tasks?${params.toString()}`);
    statusText.style.display = "none";

    document.getElementById("result-count").textContent = `${res.total} task${res.total === 1 ? "" : "s"} total`;
    document.getElementById("page-indicator").textContent = `Page ${res.page} of ${Math.max(res.total_pages, 1)}`;
    document.getElementById("prev-page").disabled = res.page <= 1;
    document.getElementById("next-page").disabled = res.page >= res.total_pages;

    const list = document.getElementById("history-list");
    if (res.items.length === 0) {
      list.innerHTML = `<div class="empty-state"><h3>No matching tasks</h3><p>Try a different search or filter.</p></div>`;
      return;
    }

    list.innerHTML = res.items
      .map(
        (task) => `
      <a href="livemonitor.html?task=${task.id}" class="history__row">
        <div class="history__row-main">
          <span class="history__row-title">${escapeHtml(task.title)}</span>
          <span class="history__row-sub">${escapeHtml(task.language || "unspecified")} · created ${new Date(task.created_at).toLocaleString()}</span>
        </div>
        <div class="history__row-meta">
          ${task.review_score != null ? `<span class="mono">${task.review_score.toFixed(1)}/10</span>` : ""}
          ${statusPill(task.status)}
        </div>
      </a>`,
      )
      .join("");
  } catch (err) {
    statusText.style.display = "block";
    statusText.textContent = err instanceof Error ? err.message : "Couldn't load history.";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = await requireAuth();
  if (!token) return;
  renderSidebar("history.html");
  loadHistory();

  document.getElementById("search").addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      page = 1;
      loadHistory();
    }, 350); // debounced so every keystroke doesn't fire a request
  });

  document.getElementById("status-filter").addEventListener("change", () => {
    page = 1;
    loadHistory();
  });

  document.getElementById("prev-page").addEventListener("click", () => {
    if (page > 1) { page -= 1; loadHistory(); }
  });
  document.getElementById("next-page").addEventListener("click", () => {
    page += 1; loadHistory();
  });
});
