// frontend/src/components/Logo.tsx
/**
 * The pixel-mark logo referenced throughout the spec ("the uploaded
 * pixel-mark logo — dark variant on dark surfaces, inverted on light") is
 * a real brand asset, not something to redraw from a description. This
 * component is the slot it goes in — drop the two files in
 * src/assets/logo/ and it renders immediately, no code changes needed.
 *
 * Until those files exist, it renders an honest placeholder instead of a
 * guessed-at mark, so it's obvious in the UI (not just in a code comment)
 * that the real asset hasn't been wired in yet.
 *
 * Expected files (add these yourself, then flip HAS_LOGO_ASSET to true):
 *   src/assets/logo/mark-dark-bg.png   — the mark as uploaded, for dark surfaces
 *   src/assets/logo/mark-light-bg.png  — tonally inverted, for light surfaces
 */
import "./Logo.css";

// Flip this once the two files above actually exist in the repo.
const HAS_LOGO_ASSET = true; // false;

// Swap these two imports in once HAS_LOGO_ASSET is true:
 import markDark from "../assets/logo/mark-dark-bg.png";
 import markLight from "../assets/logo/mark-light-bg.png";

interface LogoProps {
  /** Which surface the mark sits on — picks the dark-bg or light-bg export. */
  surface: "dark" | "light";
  size?: number;
  showWordmark?: boolean;
}

export function Logo({ surface, size = 32, showWordmark = true }: LogoProps) {
  return (
    <span className="logo" data-surface={surface} style={{ ["--logo-size" as string]: `${size}px` }}>
      {HAS_LOGO_ASSET ? (
        <img
          className="logo__mark"
           src={surface === "dark" ? markDark : markLight}
          alt="Agent X"
          width={size}
          height={size}
        />
      ) : (
        <span
          className="logo__placeholder"
          data-icon="agentx-logo-mark"
          title="Logo asset not wired in yet — see src/components/Logo.tsx"
          aria-hidden="true"
        >
          AX
        </span>
      )}
      {showWordmark && <span className="logo__wordmark">AGENT X</span>}
    </span>
  );
}
