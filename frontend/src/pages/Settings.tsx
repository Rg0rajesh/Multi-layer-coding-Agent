// frontend/src/pages/Settings.tsx
// Spec page 13: left nav + right content, one route per section. Kept as
// client-side tab state rather than real sub-routes — nothing here needs
// to be independently linkable yet, and it avoids a router config for
// seven near-identical panels.
import { useEffect, useState, type FormEvent } from "react";
import { Sidebar } from "../components";
import { api } from "../api";
import { ApiError } from "../api/client";
import "./Settings.css";

const SECTIONS = ["General", "Agents", "API Keys", "Integrations", "Notifications", "Security", "Danger Zone"] as const;
type Section = (typeof SECTIONS)[number];

interface SessionRow {
  id: string;
  device_info: string | null;
  ip_address: string | null;
  is_current: boolean;
  created_at: string;
}

export default function Settings() {
  const [active, setActive] = useState<Section>("Security");
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [twoFaEnabled, setTwoFaEnabled] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);

  useEffect(() => {
    if (active !== "Security") return;
    api.get<SessionRow[]>("/settings/sessions").then(setSessions).catch(() => {});
  }, [active]);

  async function revokeSession(sessionId: string) {
    try {
      await api.delete(`/settings/sessions/${sessionId}`);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    } catch {
      // session list just won't update — not worth a toast for this
    }
  }

  async function handlePasswordChange(event: FormEvent) {
    event.preventDefault();
    setPasswordMessage(null);
    try {
      await api.post("/settings/change-password", { current_password: currentPassword, new_password: newPassword });
      setPasswordMessage("Password updated.");
      setCurrentPassword("");
      setNewPassword("");
    } catch (err) {
      setPasswordMessage(err instanceof ApiError ? err.message : "Couldn't change your password.");
    }
  }

  async function toggleTwoFa() {
    try {
      const result = await api.patch<{ two_fa_enabled: boolean }>("/settings/two-factor", {
        enabled: !twoFaEnabled,
      });
      setTwoFaEnabled(result.two_fa_enabled);
    } catch {
      // leave the toggle as-is on failure
    }
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <div className="page-header">
          <h1>Settings</h1>
        </div>

        <div className="settings__layout">
          <nav className="settings__nav">
            {SECTIONS.map((section) => (
              <button
                key={section}
                type="button"
                className={`settings__nav-item${active === section ? " is-active" : ""}`}
                onClick={() => setActive(section)}
              >
                {section}
              </button>
            ))}
          </nav>

          <section className="settings__content card">
            {active === "Security" && (
              <>
                <h2>Password</h2>
                <form className="settings__form" onSubmit={handlePasswordChange}>
                  <input
                    type="password"
                    placeholder="Current password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                  />
                  <input
                    type="password"
                    placeholder="New password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                  />
                  <button type="submit" className="btn btn--fill">
                    Update password
                  </button>
                  {passwordMessage && <p className="settings__message">{passwordMessage}</p>}
                </form>

                <h2>Two-Factor Authentication</h2>
                <label className="settings__toggle-row">
                  <span>{twoFaEnabled ? "Enabled" : "Disabled"}</span>
                  <input type="checkbox" checked={twoFaEnabled} onChange={toggleTwoFa} />
                </label>

                <h2>Active Sessions</h2>
                <div className="settings__sessions">
                  {sessions.map((session) => (
                    <div key={session.id} className="settings__session-row">
                      <div>
                        <strong>{session.device_info ?? "Unknown device"}</strong>
                        <span className="settings__session-meta">
                          {session.ip_address ?? "—"} · {session.is_current ? "This device" : "Other device"}
                        </span>
                      </div>
                      {!session.is_current && (
                        <button className="btn" onClick={() => revokeSession(session.id)}>
                          Revoke
                        </button>
                      )}
                    </div>
                  ))}
                  {sessions.length === 0 && <p className="settings__message">No other active sessions.</p>}
                </div>
              </>
            )}

            {active === "Danger Zone" && (
              <div className="settings__danger">
                <h2>Danger Zone</h2>
                <p>Deleting your account removes every task, project, and generated file permanently.</p>
                <button className="btn" disabled>
                  Delete account
                </button>
              </div>
            )}

            {active !== "Security" && active !== "Danger Zone" && (
              <p className="settings__message">This section isn't wired up to the backend yet.</p>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
