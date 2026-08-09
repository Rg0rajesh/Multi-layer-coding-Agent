// frontend/src/pages/Login.tsx
/**
 * Auth gateway — one page, two modes. Matches Frontend Spec page 02:
 * split layout on desktop (log-stream panel + form), single column on
 * mobile, weight/glyph-based validation states instead of color (this
 * is the black & white edition — no red/green anywhere).
 */
import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useTypewriter } from "../hooks/useTypewriter";
import "./Login.css";

type AuthMode = "login" | "signup";
type StrengthLabel = "weak" | "fair" | "strong" | "very-strong";

interface FormState {
  fullName: string;
  email: string;
  password: string;
  confirmPassword: string;
  agreedToTerms: boolean;
}

interface FormErrors {
  fullName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
  terms?: string;
  form?: string;
}

const EMPTY_FORM: FormState = {
  fullName: "",
  email: "",
  password: "",
  confirmPassword: "",
  agreedToTerms: false,
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// Mirrors the log-line format from the spec appendix (agent · mark · level
// · message). Purely decorative here — just gives the left panel something
// true-to-the-product to type out instead of lorem ipsum.
const DEMO_LOG_LINES = [
  "SYSTEM · INIT   Pipeline initialised. 4 agents standing by.",
  "PLANNER ✦ TASK  Received: Build JWT auth API in TypeScript",
  "PLANNER ✦ EXEC  Decomposing into 6 subtasks...",
  "CODER ■ TASK   Received subtask 1: Setup Express server",
  "CODER ■ DONE   server.ts complete. 127 lines written.",
  "TESTER • DONE  12/12 tests passed. Passing to Reviewer.",
  "REVIEWER » DONE  Review complete. Score: 8.7/10.",
];

const STRENGTH_LABELS: Record<StrengthLabel, string> = {
  weak: "Weak",
  fair: "Fair",
  strong: "Strong",
  "very-strong": "Very Strong",
};

/** 0-4 segments filled, based on length + character variety. Not trying to
 * be a real entropy calculator — just enough signal to nudge people toward
 * a longer, mixed-character password. */
function getPasswordStrength(password: string): { score: number; label: StrengthLabel } {
  let score = 0;
  if (password.length >= 8) score += 1;
  if (password.length >= 12) score += 1;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
  if (/\d/.test(password) && /[^A-Za-z0-9]/.test(password)) score += 1;

  const labels: StrengthLabel[] = ["weak", "weak", "fair", "strong", "very-strong"];
  return { score, label: labels[score] };
}

export default function Login() {
  const navigate = useNavigate();
  const { login, register } = useAuth();

  const [mode, setMode] = useState<AuthMode>("login");
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { completedLines, currentText } = useTypewriter(DEMO_LOG_LINES);
  const passwordStrength = useMemo(() => getPasswordStrength(form.password), [form.password]);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    // Clear that field's error the moment someone starts fixing it — waiting
    // for the next submit to clear a stale error message feels broken.
    setErrors((prev) => ({ ...prev, [key]: undefined, form: undefined }));
  }

  function switchMode(nextMode: AuthMode) {
    if (nextMode === mode) return;
    setMode(nextMode);
    setErrors({});
  }

  function validate(): FormErrors {
    const next: FormErrors = {};

    if (!EMAIL_PATTERN.test(form.email)) {
      next.email = "Enter a valid email address";
    }
    if (form.password.length < 8) {
      next.password = "Password must be at least 8 characters";
    }

    if (mode === "signup") {
      if (form.fullName.trim().length < 2) {
        next.fullName = "Enter your full name";
      }
      if (form.confirmPassword !== form.password) {
        next.confirmPassword = "Passwords don't match";
      }
      if (!form.agreedToTerms) {
        next.terms = "You need to accept the terms to continue";
      }
    }

    return next;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();

    const validationErrors = validate();
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setIsSubmitting(true);
    try {
      if (mode === "login") {
        await login(form.email, form.password);
      } else {
        await register(form.email, form.password, form.fullName.trim());
      }
      navigate("/dashboard");
    } catch (err) {
      // useAuth already turns ApiError into a readable message — just
      // surface it. A generic fallback covers anything that isn't.
      setErrors({ form: err instanceof Error ? err.message : "Something went wrong — try again" });
    } finally {
      setIsSubmitting(false);
    }
  }

  function startOAuth(provider: "github" | "google") {
    const clientId =
      provider === "github" ? import.meta.env.VITE_GITHUB_CLIENT_ID : import.meta.env.VITE_GOOGLE_CLIENT_ID;

    if (!clientId) {
      // Fails loud in dev instead of redirecting to a 404 with no client_id.
      setErrors({ form: `${provider === "github" ? "GitHub" : "Google"} sign-in isn't configured yet` });
      return;
    }

    const redirectUri = `${window.location.origin}/auth/${provider}/callback`;

    const authorizeUrl =
      provider === "github"
        ? `https://github.com/login/oauth/authorize?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=read:user%20user:email`
        : `https://accounts.google.com/o/oauth2/v2/auth?client_id=${clientId}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=openid%20email%20profile`;

    window.location.href = authorizeUrl;
  }

  return (
    <div className="auth-page">
      <aside className="auth-panel" aria-hidden="true">
        <div className="auth-panel__brand">AGENT X</div>
        <p className="auth-panel__tagline">
          Plan, Code, Test, and Review — automated by 4 specialised AI agents.
        </p>

        <div className="auth-panel__log">
          {completedLines.map((line, i) => (
            <div key={i} className="auth-panel__log-line">
              {line}
            </div>
          ))}
          <div className="auth-panel__log-line">
            {currentText}
            <span className="auth-panel__cursor" />
          </div>
        </div>
      </aside>

      <main className="auth-form-wrap">
        <div className="auth-form">
          <div className="auth-form__logo">AGENT X</div>

          <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "login"}
              className={`auth-tabs__item${mode === "login" ? " is-active" : ""}`}
              onClick={() => switchMode("login")}
            >
              Login
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "signup"}
              className={`auth-tabs__item${mode === "signup" ? " is-active" : ""}`}
              onClick={() => switchMode("signup")}
            >
              Sign Up
            </button>
          </div>

          <form onSubmit={handleSubmit} noValidate>
            {mode === "signup" && (
              <Field label="Full Name" error={errors.fullName}>
                <input
                  type="text"
                  value={form.fullName}
                  onChange={(e) => updateField("fullName", e.target.value)}
                  autoComplete="name"
                />
              </Field>
            )}

            <Field label="Email" error={errors.email} success={EMAIL_PATTERN.test(form.email)}>
              <input
                type="email"
                value={form.email}
                onChange={(e) => updateField("email", e.target.value)}
                autoComplete="email"
              />
            </Field>

            <Field label="Password" error={errors.password}>
              <input
                type="password"
                value={form.password}
                onChange={(e) => updateField("password", e.target.value)}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </Field>

            {mode === "signup" && (
              <>
                <PasswordStrengthMeter strength={passwordStrength} />

                <Field
                  label="Confirm Password"
                  error={errors.confirmPassword}
                  success={form.confirmPassword.length > 0 && form.confirmPassword === form.password}
                >
                  <input
                    type="password"
                    value={form.confirmPassword}
                    onChange={(e) => updateField("confirmPassword", e.target.value)}
                    autoComplete="new-password"
                  />
                </Field>

                <label className="auth-checkbox">
                  <input
                    type="checkbox"
                    checked={form.agreedToTerms}
                    onChange={(e) => updateField("agreedToTerms", e.target.checked)}
                  />
                  <span>
                    I agree to the <a href="/terms">Terms of Service</a>
                  </span>
                </label>
                {errors.terms && <p className="auth-field__error">{errors.terms}</p>}
              </>
            )}

            {errors.form && <p className="auth-form__error">{errors.form}</p>}

            <button type="submit" className="auth-submit" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Spinner />
                  Authenticating…
                </>
              ) : mode === "login" ? (
                "Log In"
              ) : (
                "Create Account"
              )}
            </button>
          </form>

          <div className="auth-divider">
            <span>or</span>
          </div>

          <div className="auth-oauth">
            <button type="button" className="auth-oauth__btn" onClick={() => startOAuth("github")}>
              <GitHubIcon />
              Continue with GitHub
            </button>
            <button type="button" className="auth-oauth__btn" onClick={() => startOAuth("google")}>
              <GoogleIcon />
              Continue with Google
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Small local building blocks. Only used on this page right now — worth
// splitting into their own files once a second form needs Field or the
// strength meter.
// ---------------------------------------------------------------------------

function Field({
  label,
  error,
  success,
  children,
}: {
  label: string;
  error?: string;
  success?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={`auth-field${error ? " has-error" : ""}${success && !error ? " has-success" : ""}`}>
      <span className="auth-field__label">{label}</span>
      <span className="auth-field__control">
        {children}
        {success && !error && (
          <span className="auth-field__check" aria-hidden="true">
            ✓
          </span>
        )}
      </span>
      {error && <span className="auth-field__error">{error}</span>}
    </label>
  );
}

function PasswordStrengthMeter({ strength }: { strength: { score: number; label: StrengthLabel } }) {
  return (
    <div className="strength-meter" aria-live="polite">
      <div className="strength-meter__bars">
        {[0, 1, 2, 3].map((segment) => (
          <span key={segment} className={`strength-meter__bar${segment < strength.score ? " is-filled" : ""}`} />
        ))}
      </div>
      <span className="strength-meter__label">{STRENGTH_LABELS[strength.label]}</span>
    </div>
  );
}

function Spinner() {
  return (
    <svg className="spinner" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
      <circle cx="12" cy="12" r="10" fill="none" strokeWidth="2.5" strokeDasharray="60" strokeLinecap="round" />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}

// Monochrome abstract mark — the spec is a strict black & white edition,
// so a full-color Google "G" would be the one colored thing on the page.
function GoogleIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.4">
      <circle cx="8" cy="8" r="6.5" />
      <path d="M8 8h4.6a4.6 4.6 0 1 1-1.4-3.4" strokeLinecap="round" />
    </svg>
  );
}