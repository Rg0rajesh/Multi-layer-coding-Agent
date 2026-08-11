// assets/layout.js
// Single source of truth for the global nav + sidebar. Every authenticated
// page includes an empty <div id="app-nav"></div> and <div id="app-sidebar">
// </div>, sets <body data-page="dashboard"> (etc.), and includes this file
// before assets/app.js. Changing a nav item means editing this file once,
// not nine HTML files.
//
// No emoji, unicode glyphs, or placeholder characters are used for icons —
// every icon position is an empty .icon-slot the user fills in with a real
// asset later.

const NAV_ITEMS = [
  { key: "dashboard",   label: "Dashboard",      href: "dashboard.html" },
  { key: "workspace",   label: "Agent Workspace",href: "workspace.html" },
  { key: "new-task",    label: "New task",       href: "new-task.html" },
  { key: "code-output", label: "Code output",    href: "code-output.html" },
  { key: "history",     label: "History",        href: "history.html" },
  { key: "error-logs",  label: "Error logs",     href: "error-logs.html" },
];

const ACCOUNT_ITEMS = [
  { key: "profile",  label: "Profile",  href: "profile.html" },
  { key: "team",     label: "Team",     href: "team.html" },
  { key: "settings", label: "Settings", href: "settings.html" },
  { key: "docs",     label: "Docs",     href: "docs.html" },
];

function renderNav(active) {
  const mount = document.getElementById("app-nav");
  if (!mount) return;
  mount.outerHTML = `
  <nav class="navbar">
    <button class="icon-btn nav-toggle" data-sidebar-toggle aria-label="Toggle menu"><span class="icon-slot"></span></button>
    <a href="dashboard.html" class="nav-brand"><span class="nav-mark">AX</span> AGENT X</a>
    <div class="nav-right">
      <span class="mono text-dim" id="nav-task-label" style="font-size:12px;"></span>
      <button class="icon-btn rail-toggle" id="rail-toggle-btn" aria-label="Pipeline status"><span class="icon-slot"></span></button>
      <button class="icon-btn" aria-label="Notifications"><span class="icon-slot"></span></button>
      <button class="icon-btn" data-theme-toggle aria-label="Toggle theme"><span class="icon-slot"></span></button>
      <a href="profile.html" class="avatar">JD</a>
      <a href="login.html" class="icon-btn" aria-label="Log out"><span class="icon-slot"></span></a>
    </div>
  </nav>`;
}

function renderSidebar(active) {
  const mount = document.getElementById("app-sidebar");
  if (!mount) return;
  const link = (item) => `
    <a class="side-link${item.key === active ? " is-active" : ""}" href="${item.href}">
      <span class="icon-slot"></span>${item.label}
    </a>`;
  mount.outerHTML = `
  <aside class="sidebar">
    ${NAV_ITEMS.map(link).join("")}
    <div class="side-section-label">Account</div>
    ${ACCOUNT_ITEMS.map(link).join("")}
    <div class="sidebar-footer">
      <span class="avatar">JD</span>
      <div><small style="color:var(--text)">Jordan Diaz</small><small>Free plan</small></div>
    </div>
  </aside>`;
}

function initLayout() {
  const page = document.body.dataset.page || "";
  renderNav(page);
  renderSidebar(page);
}

document.addEventListener("DOMContentLoaded", initLayout);
