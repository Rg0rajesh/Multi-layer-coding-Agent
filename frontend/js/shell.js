// js/shell.js
// Shared by every protected page (Dashboard, New Task, Live Monitor, Code
// Output, History, Error Logs, Settings, Profile, Docs, Team). Renders the
// same sidebar Sidebar.tsx did, guards the page the same way RequireAuth
// did in the original App.tsx, and wires the logout button once instead
// of once per page.

const NAV_ITEMS = [
  { href: "dashboard.html", label: "Dashboard", mark: "◆" },
  { href: "newtask.html", label: "New Task", mark: "+" },
  { href: "livemonitor.html", label: "Live Monitor", mark: "●" },
  { href: "history.html", label: "History", mark: "≡" },
  { href: "errorlogs.html", label: "Error Logs", mark: "!" },
  { href: "team.html", label: "Team", mark: "§" },
  { href: "docs.html", label: "Docs", mark: "?" },
];

function renderSidebar(activePage) {
  const root = document.getElementById("sidebar-root");
  if (!root) return;

  const links = NAV_ITEMS.map(
    (item) => `
    <a href="${item.href}" class="sidebar__link${item.href === activePage ? " is-active" : ""}">
      <span class="sidebar__mark" aria-hidden="true">${item.mark}</span>${item.label}
    </a>`,
  ).join("");

  root.innerHTML = `
    <aside class="sidebar">
      <div class="sidebar__brand">AGENT X</div>
      <nav class="sidebar__nav">${links}</nav>
      <div class="sidebar__footer">
        <a href="profile.html" class="sidebar__profile">
          <span class="sidebar__avatar" id="shell-avatar">?</span>
          <span class="sidebar__profile-text">
            <span class="sidebar__profile-name" id="shell-name">Loading…</span>
            <span class="sidebar__profile-email" id="shell-email"></span>
          </span>
        </a>
        <a href="settings.html" class="sidebar__link sidebar__link--settings">Settings</a>
        <button type="button" class="sidebar__logout" id="shell-logout">Sign out</button>
      </div>
    </aside>`;

  const cachedUser = sessionStorage.getItem("agentx_user");
  if (cachedUser) {
    const user = JSON.parse(cachedUser);
    document.getElementById("shell-avatar").textContent = (user.fullName || "?").charAt(0).toUpperCase();
    document.getElementById("shell-name").textContent = user.fullName || "Guest";
    document.getElementById("shell-email").textContent = user.email || "";
  }

  document.getElementById("shell-logout").addEventListener("click", async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      setAccessToken(null);
      sessionStorage.removeItem("agentx_user");
      window.location.href = "login.html";
    }
  });
}

// Same session-recovery flow as RequireAuth in App.tsx: the in-memory
// access token is gone on a hard reload, so every protected page re-derives
// it from the httpOnly refresh cookie before rendering anything else.
async function requireAuth() {
  const token = await refreshAccessToken();
  if (!token) {
    window.location.href = "login.html";
    return null;
  }
  return token;
}
