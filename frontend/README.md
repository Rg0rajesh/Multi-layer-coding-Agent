# AGENT X — Vanilla HTML/CSS/JS Frontend

Converted from the original React/Vite frontend. Same CSS files (copied
unmodified), same markup structure, same class names — no redesign.

All 12 original pages are included.

## Running it

No build step, no npm install, no Docker.

```bash
cd vanilla-frontend
python3 -m http.server 3000
# or: npx serve -l 3000
```

Open http://localhost:3000/index.html

## Connecting to the backend

`js/api.js` talks to `http://localhost:8000` directly via `fetch()`.
No proxy involved — confirmed against `backend/config.py`,
`docker-compose.yml`, and `.env.example`, and tested live against a
running instance of the real backend.

Start the backend the normal way. As long as it's listening on :8000,
this frontend reaches it. Different port? Change one line:

```js
// js/api.js
const API_BASE_URL = "http://localhost:8000"; // <-- change this
```

## Pages (all 12, matching the original)

| Page | File | Backend calls |
|---|---|---|
| Home | `index.html` | none (marketing page) |
| Login / Signup | `login.html` | `/auth/register`, `/auth/login` |
| Dashboard | `dashboard.html` | `/tasks` |
| New Task | `newtask.html` | `POST /tasks` |
| Live Monitor | `livemonitor.html` | `/tasks/:id`, `ws://.../ws/task/:id` |
| Code Output | `codeoutput.html` | `/tasks/:id/outputs/tree`, `/outputs/:id`, `/outputs/download/zip` |
| History | `history.html` | `/tasks` (filtered, paginated, debounced search) |
| Error Logs | `errorlogs.html` | `/tasks/:id/logs`, `PATCH .../resolve` |
| Settings | `settings.html` | `/settings/sessions`, `/change-password`, `/two-factor` |
| Profile | `profile.html` | `GET/PATCH /profile` |
| Team | `team.html` | `/teams`, `/teams/:id/members` |
| Docs | `docs.html` | none (static content, same as the original) |

Every protected page (everything except Home and Login) shares:

- `js/shell.js` — renders the sidebar, guards the page behind auth
  (re-derives the session from the refresh cookie, same as `RequireAuth`
  did in the original `App.tsx`), wires the logout button
- `js/api.js` — the `fetch()` wrapper: auth headers, 401 → auto-refresh → retry
- `js/theme.js` — light/dark toggle (Home page only, matches `useTheme.ts`)

## Fonts

The original React app never actually loads its named fonts ("Mochesa",
"Athelas", etc.) — no `@font-face`, no font CDN link anywhere in the
original `index.html`. It already renders in browser fallback fonts
(Georgia / system-ui / ui-monospace) in every real browser. Since the CSS
here is copied unchanged, this version behaves identically.

## Known gaps (be aware before you rely on these)

- **GitHub/Google OAuth buttons** are wired up to match the original's
  redirect logic exactly, but there are no real OAuth app credentials to
  test against — untested.
- **Live Monitor's WebSocket** is a faithful port of the original
  `useWebSocket.ts` + `useAgentStream.ts` (same reconnect backoff, same
  `AGENT_COLORS` map, same 500-line cap) but wasn't exercised against a
  real live agent run — that needs Ollama + a running Celery worker, which
  weren't available in the environment this was built in.
- Every REST endpoint every page calls **was** tested live against the
  real backend — signup, login, profile, tasks (create/list/filter/search),
  agent runs, code output tree, logs, settings sessions, and teams all
  returned real, correct data.

## Files

```
index.html / login.html / dashboard.html / newtask.html / livemonitor.html
codeoutput.html / history.html / errorlogs.html / settings.html
profile.html / team.html / docs.html

css/            Copied unchanged from the original React app
js/api.js       fetch() wrapper — auth headers, token refresh
js/auth.js      Login/signup form logic
js/shell.js     Shared sidebar + auth guard + logout
js/theme.js     Light/dark toggle
js/dashboard.js / newtask.js / livemonitor.js / codeoutput.js
js/history.js / errorlogs.js / settings.js / profile.js / team.js / docs.js
js/config.js    OAuth client ID placeholders
assets/logo/    Same PNG files as the original
```
