// js/settings.js

async function loadSessions() {
  const list = document.getElementById("sessions-list");
  try {
    const sessions = await api.get("/settings/sessions");
    list.innerHTML = sessions
      .map(
        (s) => `
      <div class="settings__session-row">
        <span>${s.device_info || "Unknown device"}${s.is_current ? " (this device)" : ""}</span>
        <span class="mono">${s.ip_address || ""}</span>
        ${!s.is_current ? `<button type="button" class="settings__revoke-btn" data-id="${s.id}">Revoke</button>` : ""}
      </div>`,
      )
      .join("");
    list.querySelectorAll(".settings__revoke-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await api.delete(`/settings/sessions/${btn.dataset.id}`);
        loadSessions();
      });
    });
  } catch (err) {
    list.textContent = err instanceof Error ? err.message : "Couldn't load sessions.";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = await requireAuth();
  if (!token) return;
  renderSidebar("");
  loadSessions();

  document.getElementById("revoke-others-btn").addEventListener("click", async () => {
    const res = await api.post("/settings/sessions/revoke-others");
    alert(`Signed out of ${res.revoked_count} other session(s).`);
    loadSessions();
  });

  document.getElementById("password-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errorEl = document.getElementById("password-error");
    errorEl.style.display = "none";
    try {
      await api.post("/settings/change-password", {
        current_password: document.getElementById("current-password").value,
        new_password: document.getElementById("new-password").value,
      });
      alert("Password updated.");
      e.target.reset();
    } catch (err) {
      errorEl.style.display = "block";
      errorEl.textContent = err instanceof Error ? err.message : "Couldn't update password.";
    }
  });

  document.getElementById("two-factor-toggle").addEventListener("change", async (e) => {
    const res = await api.patch("/settings/two-factor", { enabled: e.target.checked });
    const secretEl = document.getElementById("two-factor-secret");
    if (res.secret) {
      secretEl.style.display = "block";
      secretEl.textContent = `Secret: ${res.secret}`;
    } else {
      secretEl.style.display = "none";
    }
  });
});
