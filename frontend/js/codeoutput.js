// js/codeoutput.js

function getTaskIdFromUrl() {
  return new URLSearchParams(window.location.search).get("task");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderTreeNode(node) {
  if (node.type === "file") {
    return `<button type="button" class="codeoutput__file" data-output-id="${node.id}">${escapeHtml(node.name)}</button>`;
  }
  const children = (node.children || []).map(renderTreeNode).join("");
  return `
    <div class="codeoutput__folder">
      <span class="codeoutput__folder-name">${escapeHtml(node.name)}</span>
      <div class="codeoutput__folder-children">${children}</div>
    </div>`;
}

async function openFile(taskId, outputId) {
  document.querySelectorAll(".codeoutput__file").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.outputId === outputId);
  });

  try {
    const file = await api.get(`/tasks/${taskId}/outputs/${outputId}`);
    document.getElementById("viewer-header").textContent = file.file_path;
    document.getElementById("viewer-code").textContent = file.content;
  } catch (err) {
    document.getElementById("viewer-code").textContent =
      err instanceof Error ? `Couldn't load this file — ${err.message}` : "Couldn't load this file.";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = await requireAuth();
  if (!token) return;
  renderSidebar("");

  const taskId = getTaskIdFromUrl();
  const statusText = document.getElementById("status-text");
  if (!taskId) {
    statusText.style.display = "block";
    statusText.textContent = "No task selected — open a task from the Dashboard or History page.";
    return;
  }

  try {
    const task = await api.get(`/tasks/${taskId}`);
    document.getElementById("task-title").textContent = task.title;
  } catch (err) {
    statusText.style.display = "block";
    statusText.textContent = err instanceof Error ? err.message : "Couldn't load this task.";
    return;
  }

  document.getElementById("download-zip-link").addEventListener("click", async (e) => {
    e.preventDefault();
    const link = e.currentTarget;
    const original = link.textContent;
    link.textContent = "Preparing…";

    try {
      // A plain <a href> or window.open() can't attach the Authorization
      // header this endpoint requires, so fetch it as a blob and trigger
      // the download manually.
      const res = await fetch(`http://localhost:8000/api/v1/tasks/${taskId}/outputs/download/zip`, {
        headers: { Authorization: `Bearer ${getAccessToken()}` },
      });
      if (!res.ok) throw new Error(`Download failed (${res.status})`);

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "agentx-output.zip";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Couldn't download the ZIP.");
    } finally {
      link.textContent = original;
    }
  });

  try {
    const tree = await api.get(`/tasks/${taskId}/outputs/tree`);
    const treeEl = document.getElementById("file-tree");
    treeEl.innerHTML = (tree.children || []).map(renderTreeNode).join("") || "<p>No files generated yet.</p>";
    treeEl.querySelectorAll(".codeoutput__file").forEach((btn) => {
      btn.addEventListener("click", () => openFile(taskId, btn.dataset.outputId));
    });
  } catch (err) {
    statusText.style.display = "block";
    statusText.textContent = err instanceof Error ? err.message : "Couldn't load the file tree.";
  }
});
