# Gadziriro AI Workspace — Frontend

React + TypeScript (Vite) single-page app for the Gadziriro AI Workspace Phase 0 prototype.

## Requirements

- Node 20+ (CI uses Node 20 with `npm ci`)
- npm (this project uses npm, not pnpm, to match RUBIEM CI)

## Install

```bash
npm ci        # CI / reproducible install (uses package-lock.json)
# or, to update the lockfile:
npm install
```

## Develop

```bash
npm run dev
```

The dev server runs on Vite's default port (5173) and **proxies `/api` to the
gateway at `http://127.0.0.1:8080`** (see `vite.config.ts`). Start the backend
gateway on port 8080 so auth, sessions, installer, and audit calls resolve.

## Build & typecheck

```bash
npm run typecheck   # tsc --noEmit (strict)
npm run build       # tsc -b && vite build -> dist/
```

## Structure

- `src/api/client.ts` — typed fetch client (sends the httponly session cookie via
  `credentials: 'include'`); TS interfaces mirror the gateway schemas.
- `src/views/Login.tsx` — username/password sign-in.
- `src/views/Workspace.tsx` — session list, create/stop, cell editor + run, and the
  "No network (sealed)" privacy badge when `allow_egress` is false (FR-20).
- `src/views/Admin.tsx` — hardware report (installer) and audit-chain verify status;
  shows "admin only" when `/api/audit/verify` returns 403.
- `src/App.tsx` — state-based view switcher (Login / Workspace / Admin tabs / Logout).
