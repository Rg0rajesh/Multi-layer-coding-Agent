// frontend/src/components/Sidebar.tsx
import { NavLink } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import "./Sidebar.css";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", mark: "◆" },
  { to: "/tasks/new", label: "New Task", mark: "+" },
  { to: "/runner", label: "Code Runner", mark: "▶" },
  { to: "/monitor", label: "Live Monitor", mark: "●" },
  { to: "/history", label: "History", mark: "≡" },
  { to: "/errors", label: "Error Logs", mark: "!" },
  { to: "/team", label: "Team", mark: "§" },
  { to: "/docs", label: "Docs", mark: "?" },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  return <aside className="sidebar">
    <div className="sidebar__brand">AGENT X</div>
    <nav className="sidebar__nav">{NAV_ITEMS.map((item) => <NavLink key={item.to} to={item.to} className={({ isActive }) => `sidebar__link${isActive ? " is-active" : ""}`}><span className="sidebar__mark" aria-hidden="true">{item.mark}</span>{item.label}</NavLink>)}</nav>
    <div className="sidebar__footer">
      <NavLink to="/profile" className="sidebar__profile"><span className="sidebar__avatar">{(user?.fullName ?? "?").charAt(0).toUpperCase()}</span><span className="sidebar__profile-text"><span className="sidebar__profile-name">{user?.fullName ?? "Guest"}</span><span className="sidebar__profile-email">{user?.email ?? ""}</span></span></NavLink>
      <NavLink to="/settings" className="sidebar__link sidebar__link--settings">Settings</NavLink>
      <button type="button" className="sidebar__logout" onClick={logout}>Sign out</button>
    </div>
  </aside>;
}
