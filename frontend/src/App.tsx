// frontend/src/App.tsx
// Route table for all 12 pages. AuthProvider wraps everything so useAuth
// is available before the router even resolves a path — RequireAuth below
// depends on that being true on first render, not after some effect fires.
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "./hooks/useAuth";

import Home from "./pages/Home";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import NewTask from "./pages/NewTask";
import LiveMonitor from "./pages/LiveMonitor";
import CodeOutput from "./pages/CodeOutput";
import History from "./pages/History";
import ErrorLogs from "./pages/ErrorLogs";
import Settings from "./pages/Settings";
import Profile from "./pages/Profile";
import Docs from "./pages/Docs";
import Team from "./pages/Team";

import "./styles/theme.css";

function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) return null; // avoid a login-page flash while the refresh cookie is checked
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />

          <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
          <Route path="/tasks/new" element={<RequireAuth><NewTask /></RequireAuth>} />
          <Route path="/monitor" element={<RequireAuth><LiveMonitor /></RequireAuth>} />
          <Route path="/output" element={<RequireAuth><CodeOutput /></RequireAuth>} />
          <Route path="/history" element={<RequireAuth><History /></RequireAuth>} />
          <Route path="/errors" element={<RequireAuth><ErrorLogs /></RequireAuth>} />
          <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
          <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
          <Route path="/docs" element={<RequireAuth><Docs /></RequireAuth>} />
          <Route path="/team" element={<RequireAuth><Team /></RequireAuth>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
