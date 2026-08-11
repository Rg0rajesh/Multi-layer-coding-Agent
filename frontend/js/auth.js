// js/auth.js — powers login.html
// Same validation rules as the original Login.tsx: email regex, 8-char
// minimum password, confirm-password match, and required terms checkbox
// on signup. Same password-strength scoring too.

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const STRENGTH_LABELS = ["Weak", "Weak", "Fair", "Strong", "Very Strong"];

function getPasswordStrength(password) {
  let score = 0;
  if (password.length >= 8) score += 1;
  if (password.length >= 12) score += 1;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1;
  return { score, label: STRENGTH_LABELS[score] };
}

const state = {
  mode: "login", // "login" | "signup"
};

function $(selector) {
  return document.querySelector(selector);
}

function switchMode(nextMode) {
  if (nextMode === state.mode) return;
  state.mode = nextMode;

  $("#tab-login").setAttribute("aria-selected", String(nextMode === "login"));
  $("#tab-login").classList.toggle("is-active", nextMode === "login");
  $("#tab-signup").setAttribute("aria-selected", String(nextMode === "signup"));
  $("#tab-signup").classList.toggle("is-active", nextMode === "signup");

  document.querySelectorAll("[data-signup-only]").forEach((el) => {
    el.style.display = nextMode === "signup" ? "" : "none";
  });

  $("#submit-btn").textContent = nextMode === "login" ? "Log In" : "Create Account";
  clearErrors();
}

function clearErrors() {
  document.querySelectorAll(".auth-field__error, .auth-form__error").forEach((el) => {
    el.textContent = "";
    el.style.display = "none";
  });
  document.querySelectorAll(".auth-field").forEach((el) => {
    el.classList.remove("has-error", "has-success");
  });
}

function showFieldError(fieldId, message) {
  const field = document.getElementById(fieldId);
  field.closest(".auth-field")?.classList.add("has-error");
  const errorEl = field.closest(".auth-field")?.querySelector(".auth-field__error");
  if (errorEl) {
    errorEl.textContent = message;
    errorEl.style.display = "block";
  }
}

function showFormError(message) {
  const el = $("#form-error");
  el.textContent = message;
  el.style.display = "block";
}

function updateStrengthMeter() {
  const password = $("#password").value;
  const { score, label } = getPasswordStrength(password);
  document.querySelectorAll(".strength-meter__bar").forEach((bar, i) => {
    bar.classList.toggle("is-filled", i < score);
  });
  $("#strength-label").textContent = label;
}

function validate() {
  clearErrors();
  let valid = true;

  const email = $("#email").value;
  const password = $("#password").value;

  if (!EMAIL_PATTERN.test(email)) {
    showFieldError("email", "Enter a valid email address");
    valid = false;
  }
  if (password.length < 8) {
    showFieldError("password", "Password must be at least 8 characters");
    valid = false;
  }

  if (state.mode === "signup") {
    const fullName = $("#full-name").value.trim();
    const confirmPassword = $("#confirm-password").value;
    const agreed = $("#agree-terms").checked;

    if (fullName.length < 2) {
      showFieldError("full-name", "Enter your full name");
      valid = false;
    }
    if (confirmPassword !== password) {
      showFieldError("confirm-password", "Passwords don't match");
      valid = false;
    }
    if (!agreed) {
      showFormError("You need to accept the terms to continue");
      valid = false;
    }
  }

  return valid;
}

async function handleSubmit(event) {
  event.preventDefault();
  if (!validate()) return;

  const submitBtn = $("#submit-btn");
  submitBtn.disabled = true;
  submitBtn.textContent = state.mode === "login" ? "Authenticating…" : "Creating account…";

  try {
    let data;
    if (state.mode === "login") {
      data = await api.post(
        "/auth/login",
        { email: $("#email").value, password: $("#password").value },
        { skipAuth: true },
      );
    } else {
      data = await api.post(
        "/auth/register",
        {
          email: $("#email").value,
          password: $("#password").value,
          full_name: $("#full-name").value.trim(),
        },
        { skipAuth: true },
      );
    }

    setAccessToken(data.access_token);
    // Same storage strategy as the React app: nothing in localStorage.
    // Dashboard re-derives the session via /auth/refresh on load.
    sessionStorage.setItem("agentx_user", JSON.stringify({
      id: data.user_id,
      email: data.email,
      fullName: data.full_name,
    }));

    window.location.href = "dashboard.html";
  } catch (err) {
    showFormError(err instanceof Error ? err.message : "Something went wrong — try again");
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = state.mode === "login" ? "Log In" : "Create Account";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("#tab-login").addEventListener("click", () => switchMode("login"));
  $("#tab-signup").addEventListener("click", () => switchMode("signup"));
  $("#password").addEventListener("input", updateStrengthMeter);
  $("#auth-form").addEventListener("submit", handleSubmit);
  $("#github-oauth-btn").addEventListener("click", () => startOAuth("github"));
  $("#google-oauth-btn").addEventListener("click", () => startOAuth("google"));
});

// Same redirect construction as the original Login.tsx::startOAuth. Client
// IDs are read from window.AGENTX_CONFIG (set in config.js) instead of
// import.meta.env, since there's no bundler here.
function startOAuth(provider) {
  const clientId =
    provider === "github"
      ? window.AGENTX_CONFIG.GITHUB_CLIENT_ID
      : window.AGENTX_CONFIG.GOOGLE_CLIENT_ID;

  if (!clientId) {
    showFormError(`${provider === "github" ? "GitHub" : "Google"} sign-in isn't configured yet`);
    return;
  }

  const redirectUri = `${window.location.origin}/auth/${provider}/callback`;
  const authorizeUrl =
    provider === "github"
      ? `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=read:user%20user:email`
      : `https://accounts.google.com/o/oauth2/v2/auth?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=openid%20email%20profile`;

  window.location.href = authorizeUrl;
}
