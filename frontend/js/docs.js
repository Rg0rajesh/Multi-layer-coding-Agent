// js/docs.js — tab switching only, no API calls (matches the original,
// which hardcodes this content rather than fetching it — see Docs.tsx's
// own comment about not pulling in a Markdown lib for four short sections)

document.addEventListener("DOMContentLoaded", async () => {
  const token = await requireAuth();
  if (!token) return;
  renderSidebar("docs.html");

  document.querySelectorAll(".docs__nav-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".docs__nav-item").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");

      const target = btn.dataset.section;
      document.querySelectorAll("[data-panel]").forEach((panel) => {
        panel.style.display = panel.dataset.panel === target ? "" : "none";
      });
    });
  });
});
