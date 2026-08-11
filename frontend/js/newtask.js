// js/newtask.js

function $(id) { return document.getElementById(id); }

function showError(message) {
  const el = $("form-error");
  el.textContent = message;
  el.style.display = "block";
}

async function handleSubmit(event) {
  event.preventDefault();
  const title = $("title").value.trim();
  if (title.length === 0) {
    showError("Give the task a title before starting it.");
    return;
  }

  const btn = $("submit-btn");
  btn.disabled = true;
  btn.textContent = "Starting…";

  try {
    const task = await api.post("/tasks", {
      title,
      description: $("description").value.trim() || null,
      language: $("language").value,
      priority: $("priority").value,
      max_exec_minutes: Number($("max-minutes").value) || 10,
      git_integration: $("git-integration").checked,
    });
    window.location.href = `livemonitor.html?task=${task.id}`;
  } catch (err) {
    showError(err instanceof Error ? err.message : "Couldn't start the task — try again.");
    btn.disabled = false;
    btn.textContent = "Start Task";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = await requireAuth();
  if (!token) return;
  renderSidebar("newtask.html");
  $("new-task-form").addEventListener("submit", handleSubmit);
});
