// js/theme.js — shared by every page
const THEME_KEY = "agentx-theme";

function systemPrefersDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function resolveTheme(mode) {
  return mode === "system" ? (systemPrefersDark() ? "dark" : "light") : mode;
}

function applyTheme(resolved) {
  document.documentElement.setAttribute("data-theme", resolved);
  document.querySelectorAll(".logo").forEach((el) => el.setAttribute("data-surface", resolved));
  document.querySelectorAll(".logo__mark").forEach((img) => {
    img.src = resolved === "dark" ? "assets/logo/mark-dark-bg.png" : "assets/logo/mark-light-bg.png";
  });
  const toggle = document.getElementById("theme-toggle");
  if (toggle) toggle.textContent = resolved === "dark" ? "☾" : "☀";
}

function getStoredMode() {
  return localStorage.getItem(THEME_KEY) || "system";
}

function setMode(mode) {
  localStorage.setItem(THEME_KEY, mode);
  applyTheme(resolveTheme(mode));
}

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(resolveTheme(getStoredMode()));

  const toggle = document.getElementById("theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      const current = resolveTheme(getStoredMode());
      setMode(current === "dark" ? "light" : "dark");
    });
  }

  const navbar = document.getElementById("navbar");
  if (navbar) {
    window.addEventListener(
      "scroll",
      () => navbar.classList.toggle("is-scrolled", window.scrollY > 80),
      { passive: true },
    );
  }
});
