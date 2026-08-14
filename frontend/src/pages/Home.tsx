// frontend/src/pages/Home.tsx
// Unauthenticated marketing/landing page — the one page in the app
// that isn't behind the sidebar shell. Redirects straight to Dashboard
// for anyone who's already logged in.
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { Navbar } from "../components";
import "./Home.css";

export default function Home() {
  const { isAuthenticated, isLoading } = useAuth();

  if (!isLoading && isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return (
    <div className="home">
      <Navbar ctaLabel="Start Building Free" ctaTo="/login" />

      <section className="home__hero">
        <h1>
          Plan, Code, Test, and Review —<br />
          automated by 10 specialised agents.
        </h1>
        <p>
          Guardrail screens every request. Grounding checks plans against your actual repo. A human
          approves before anything ships. Nothing here is a black box.
        </p>
        <Link to="/login" className="btn btn--fill home__cta">
          Start building
        </Link>
      </section>

      <section className="home__pipeline">
        {["GUARDRAIL", "PLANNER", "GROUNDING", "HUMAN", "CODER", "TESTER", "SECURITY", "REVIEWER"].map((agent) => (
          <span key={agent} className="home__pipeline-step">
            {agent}
          </span>
        ))}
      </section>
    </div>
  );
}
