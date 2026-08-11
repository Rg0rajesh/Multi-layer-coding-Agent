// js/profile.js

function $(id) { return document.getElementById(id); }

async function loadProfile() {
  const profile = await api.get("/profile");
  $("display-name").value = profile.display_name || "";
  $("bio").value = profile.bio || "";
  $("website-url").value = profile.website_url || "";
  $("github-url").value = profile.github_url || "";
  $("twitter-handle").value = profile.twitter_handle || "";
}

document.addEventListener("DOMContentLoaded", async () => {
  const token = await requireAuth();
  if (!token) return;
  renderSidebar("");

  try {
    await loadProfile();
  } catch (err) {
    $("form-error").style.display = "block";
    $("form-error").textContent = err instanceof Error ? err.message : "Couldn't load your profile.";
  }

  $("profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const errorEl = $("form-error");
    errorEl.style.display = "none";
    try {
      await api.patch("/profile", {
        display_name: $("display-name").value || null,
        bio: $("bio").value || null,
        website_url: $("website-url").value || null,
        github_url: $("github-url").value || null,
        twitter_handle: $("twitter-handle").value || null,
      });
      alert("Profile updated.");
    } catch (err) {
      errorEl.style.display = "block";
      errorEl.textContent = err instanceof Error ? err.message : "Couldn't save your profile.";
    }
  });
});
