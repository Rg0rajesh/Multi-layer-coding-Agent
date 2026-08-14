// frontend/src/components/Sidebar.tsx

import { NavLink } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";
import "./Sidebar.css";

const NAV_ITEMS = [
  {
    to: "/dashboard",
    label: "Dashboard",
    mark: "fa-solid fa-gauge-high",
  },
  {
    to: "/tasks/new",
    label: "New Task",
    mark: "fa-solid fa-plus",
  },
  {
    to: "/monitor",
    label: "Live Monitor",
    mark: "fa-solid fa-chart-line",
  },
  {
    to: "/history",
    label: "History",
    mark: "fa-solid fa-clock-rotate-left",
  },
  {
    to: "/errors",
    label: "Error Logs",
    mark: "fa-solid fa-triangle-exclamation",
  },
  {
    to: "/team",
    label: "Team",
    mark: "fa-solid fa-users",
  },
  {
    to: "/docs",
    label: "Docs",
    mark: "fa-solid fa-book",
  },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  const { resolved, toggle } = useTheme();

  return (
    <aside className="sidebar">
      <div className="sidebar__brand-row">
        <span className="sidebar__brand">AGENT X</span>

        <button
          type="button"
          className="sidebar__theme-toggle"
          onClick={toggle}
          aria-label={`Switch to ${
            resolved === "dark" ? "light" : "dark"
          } mode`}
          title={`Switch to ${
            resolved === "dark" ? "light" : "dark"
          } mode`}
        >
          <i
            className={
              resolved === "dark"
                ? "fa-solid fa-sun"
                : "fa-solid fa-moon"
            }
          />
        </button>
      </div>

      <nav className="sidebar__nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `sidebar__link${isActive ? " is-active" : ""}`
            }
          >
            <span className="sidebar__mark" aria-hidden="true">
              <i className={item.mark} />
            </span>

            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar__footer">
        <NavLink to="/profile" className="sidebar__profile">
          <span className="sidebar__avatar">
            {(user?.fullName ?? "?").charAt(0).toUpperCase()}
          </span>

          <span className="sidebar__profile-text">
            <span className="sidebar__profile-name">
              {user?.fullName ?? "Guest"}
            </span>

            <span className="sidebar__profile-email">
              {user?.email ?? ""}
            </span>
          </span>
        </NavLink>

        <NavLink
          to="/settings"
          className="sidebar__link sidebar__link--settings"
        >
          <span className="sidebar__mark" aria-hidden="true">
            <i className="fa-solid fa-gear" />
          </span>

          <span>Settings</span>
        </NavLink>

        <button
          type="button"
          className="sidebar__logout"
          onClick={logout}
        >
          <span className="sidebar__mark" aria-hidden="true">
            <i className="fa-solid fa-right-from-bracket" />
          </span>

          <span>Sign out</span>
        </button>
      </div>
    </aside>
  );
}