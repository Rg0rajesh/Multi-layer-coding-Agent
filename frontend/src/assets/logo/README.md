Drop your two logo exports here, matching the filenames already
referenced (commented out) in `src/components/Logo.tsx`:

  mark-dark-bg.png   — the mark as originally uploaded, for dark surfaces
  mark-light-bg.png  — tonally inverted, for light surfaces

Then in Logo.tsx:
  1. Uncomment the two `import` lines near the top
  2. Set `HAS_LOGO_ASSET = true`
  3. Uncomment the `src={...}` line on the <img> element

No other file needs to change — Navbar, Sidebar, and Login all render
through this one component.
