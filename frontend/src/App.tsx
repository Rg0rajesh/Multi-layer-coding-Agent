// frontend/src/App.tsx
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import NewTask from "./pages/NewTask";
import LiveMonitor from "./pages/LiveMonitor";
import CodeOutput from "./pages/CodeOutput";
import CodeRunner from "./pages/CodeRunner";
import History from "./pages/History";
import ErrorLogs from "./pages/ErrorLogs";
import Settings from "./pages/Settings";
import Profile from "./pages/Profile";
import Docs from "./pages/Docs";
import Team from "./pages/Team";
import "./styles/theme.css";

function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return <BrowserRouter><AuthProvider><Routes>
    <Route path="/" element={<Home />} />
    <Route path="/login" element={<Login />} />
    <Route path="/dashboard" element={<RequireAuth><Dashboard /></RequireAuth>} />
    <Route path="/tasks/new" element={<RequireAuth><NewTask /></RequireAuth>} />
    <Route path="/monitor" element={<RequireAuth><LiveMonitor /></RequireAuth>} />
    <Route path="/output" element={<RequireAuth><CodeOutput /></RequireAuth>} />
    <Route path="/runner" element={<RequireAuth><CodeRunner /></RequireAuth>} />
    <Route path="/history" element={<RequireAuth><History /></RequireAuth>} />
    <Route path="/errors" element={<RequireAuth><ErrorLogs /></RequireAuth>} />
    <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
    <Route path="/profile" element={<RequireAuth><Profile /></RequireAuth>} />
    <Route path="/docs" element={<RequireAuth><Docs /></RequireAuth>} />
    <Route path="/team" element={<RequireAuth><Team /></RequireAuth>} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></AuthProvider></BrowserRouter>;
}
