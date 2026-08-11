// assets/app.js — shared across every AGENT X page. No framework, no build step.

(function () {
  const STORAGE_KEY = "agentx-theme";

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    document
      .querySelectorAll("[data-theme-icon]")
      .forEach((el) => (el.textContent = theme === "dark" ? "Light" : "Dark"));
  }

  function initTheme() {
    const saved = localStorage.getItem(STORAGE_KEY);
    const preferred = saved || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    applyTheme(preferred);
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
    const next = current === "dark" ? "light" : "dark";
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  }

  // Glossy nav gets slightly more opaque/blurred once content scrolls under it —
  // matches the "reads as solid once it's over busy content" spec.
  function initNavScrollState() {
    const nav = document.querySelector(".navbar");
    if (!nav) return;
    const onScroll = () => nav.classList.toggle("is-scrolled", window.scrollY > 80);
    document.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  function initSidebarToggle() {
    const toggle = document.querySelector("[data-sidebar-toggle]");
    const sidebar = document.querySelector(".sidebar");
    if (!toggle || !sidebar) return;
    toggle.addEventListener("click", () => sidebar.classList.toggle("is-open"));
    document.addEventListener("click", (e) => {
      if (window.innerWidth > 900) return;
      if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {
        sidebar.classList.remove("is-open");
      }
    });
  }

  // Count-up used on Dashboard / Profile stat cards.
  function initCountUp() {
    document.querySelectorAll("[data-count-to]").forEach((el) => {
      const target = parseFloat(el.dataset.countTo);
      const decimals = el.dataset.countDecimals ? parseInt(el.dataset.countDecimals, 10) : 0;
      const duration = 900;
      const start = performance.now();
      function tick(now) {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = (target * eased).toFixed(decimals);
        if (progress < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initNavScrollState();
    initSidebarToggle();
    initCountUp();
    document.querySelectorAll("[data-theme-toggle]").forEach((btn) => btn.addEventListener("click", toggleTheme));
  });

  window.AgentX = { toggleTheme, applyTheme };
})();
