// js/team.js

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function loadTeams() {
  const statusText = document.getElementById("status-text");
  const list = document.getElementById("team-list");
  try {
    const teams = await api.get("/teams");
    statusText.style.display = "none";

    if (teams.length === 0) {
      list.innerHTML = `<div class="empty-state"><h3>No teams yet</h3><p>Create one to start collaborating.</p></div>`;
      return;
    }

    list.innerHTML = teams
      .map((t) => `<button type="button" class="team__row" data-id="${t.id}">${escapeHtml(t.name)}</button>`)
      .join("");
    list.querySelectorAll(".team__row").forEach((btn) => {
      btn.addEventListener("click", () => loadMembers(btn.dataset.id, btn.textContent));
    });
  } catch (err) {
    statusText.style.display = "block";
    statusText.textContent = err instanceof Error ? err.message : "Couldn't load teams.";
  }
}

async function loadMembers(teamId, teamName) {
  const section = document.getElementById("members-section");
  section.style.display = "block";
  document.getElementById("members-heading").textContent = `${teamName} — Members`;

  try {
    const members = await api.get(`/teams/${teamId}/members`);
    document.getElementById("members-list").innerHTML = members
      .map(
        (m) => `
      <div class="team__member-row">
        <span>${escapeHtml(m.full_name)}</span>
        <span class="mono">${escapeHtml(m.email)}</span>
        <span class="status-pill">${m.role}</span>
      </div>`,
      )
      .join("");
  } catch (err) {
    document.getElementById("members-list").textContent =
      err instanceof Error ? err.message : "Couldn't load members.";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = await requireAuth();
  if (!token) return;
  renderSidebar("team.html");
  loadTeams();

  document.getElementById("new-team-btn").addEventListener("click", async () => {
    const name = prompt("Team name?");
    if (!name) return;
    try {
      await api.post("/teams", { name });
      loadTeams();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Couldn't create team.");
    }
  });
});
