// frontend/src/pages/Team.tsx
// Spec page 17. Members tab wired to routers/team.py; the other three
// tabs (Shared Projects, Activity, Permissions) are stubbed rather than
// faked with placeholder data — an empty state here is honest, fake
// data isn't.
import { useEffect, useState } from "react";
import { Sidebar } from "../components";
import { api } from "../api";
import "./Team.css";

const TABS = ["Members", "Shared Projects", "Activity", "Permissions"] as const;
type Tab = (typeof TABS)[number];

interface TeamMember {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  status: string;
}

export default function Team() {
  const [tab, setTab] = useState<Tab>("Members");
  const [teamId, setTeamId] = useState<string | null>(null);
  const [members, setMembers] = useState<TeamMember[]>([]);

  useEffect(() => {
    api
      .get<{ id: string }[]>("/teams")
      .then((teams) => {
        if (teams[0]) setTeamId(teams[0].id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!teamId || tab !== "Members") return;
    api.get<TeamMember[]>(`/teams/${teamId}/members`).then(setMembers).catch(() => {});
  }, [teamId, tab]);

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <div className="page-header">
          <h1>Team</h1>
        </div>

        <div className="team__tabs">
          {TABS.map((t) => (
            <button key={t} className={`team__tab${tab === t ? " is-active" : ""}`} onClick={() => setTab(t)}>
              {t}
            </button>
          ))}
        </div>

        {!teamId ? (
          <div className="empty-state">
            <h3>No team yet</h3>
            <p>Create a team to invite collaborators and share projects.</p>
          </div>
        ) : tab === "Members" ? (
          <table className="team__table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {members.map((m) => (
                <tr key={m.id}>
                  <td>{m.full_name}</td>
                  <td>{m.email}</td>
                  <td className={`team__role team__role--${m.role}`}>{m.role}</td>
                  <td>{m.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty-state">
            <h3>Nothing here yet</h3>
            <p>{tab} isn't wired up to the backend yet.</p>
          </div>
        )}
      </main>
    </div>
  );
}
