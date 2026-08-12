// frontend/src/components/Navbar.tsx
/**
 * The glossy nav bar from the spec (page 5) — used as-is on every public
 * page. Authenticated pages use Sidebar.tsx instead; this one is for
 * Home and anywhere else outside the logged-in shell.
 *
 * The "glossy" read is built entirely from stacked translucency and one
 * specular hairline, no color — see the .navbar__sheen bands in
 * Navbar.css. Scrolling past 80px nudges the panel toward more opaque
 * and more blurred (200ms) so it reads as solid over busy page content,
 * exactly per spec.
 */
import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { Logo } from "./Logo";
import { useTheme } from "../hooks/useTheme";
import "./Navbar.css";

const SCROLL_THRESHOLD = 80;

interface NavLinkItem {
  to: string;
  label: string;
}

const LINKS: NavLinkItem[] = [
  { to: "/", label: "Home" },
  { to: "/#features", label: "Features" },
  { to: "/docs", label: "Docs" },
  { to: "/#pricing", label: "Pricing" },
];

interface NavbarProps {
  ctaLabel?: string;
  ctaTo?: string;
}

export function Navbar({ ctaLabel = "Get Started", ctaTo = "/login" }: NavbarProps) {
  const [isScrolled, setIsScrolled] = useState(false);
  const { resolved, toggle } = useTheme();

  useEffect(() => {
    const onScroll = () => setIsScrolled(window.scrollY > SCROLL_THRESHOLD);
    onScroll(); // page could already be scrolled on mount (e.g. back-navigation)
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className={`navbar${isScrolled ? " is-scrolled" : ""}`}>
      {/* Layered translucent bands stacked toward the top edge — the
          "glass highlight" read, alpha only, no gradient color. */}
      <span className="navbar__sheen" aria-hidden="true" />
      <span className="navbar__specular" aria-hidden="true" />

      <div className="navbar__inner">
        <NavLink to="/" className="navbar__brand" aria-label="Agent X home">
          <Logo surface={resolved} size={28} />
        </NavLink>

        <nav className="navbar__links" aria-label="Primary">
          {LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === "/"}
              className={({ isActive }) => `navbar__link${isActive ? " is-active" : ""}`}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>

        <div className="navbar__actions">
          <button
            type="button"
            className="navbar__theme-toggle"
            onClick={toggle}
            aria-label={`Switch to ${resolved === "dark" ? "light" : "dark"} mode`}
            title={`Switch to ${resolved === "dark" ? "light" : "dark"} mode`}
          >
            {resolved === "dark" ? "☾" : "☀"}
          </button>

          <NavLink to={ctaTo} className="navbar__cta">
            <span className="navbar__cta-sheen" aria-hidden="true" />
            {ctaLabel}
          </NavLink>
        </div>
      </div>
    </header>
  );
}
