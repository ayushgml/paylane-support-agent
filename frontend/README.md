# Paylane demo frontend

Design A: a dark navigation rail, light conversation workspace and an evidence panel. This is an optional client of the independently runnable backend.

Requires Node.js 20.19+ (or 22.12+). From this directory:

```sh
npm ci
npm run dev
```

Start the backend separately on port 8000. Vite proxies `/api` to it; no provider key belongs in this folder. Open the URL printed by Vite.

```sh
npm run build
npm test
```

Playwright uses installed Google Chrome. The browser tests require the backend on 8000 and Vite on 5173. They cover navigation, all twelve scenario entries, actual rulebook loading, initial evidence state and mobile containment. They do not claim to evaluate model quality.

For a single-origin demo, build this folder then restart `uv run paylane serve` from `backend/`: FastAPI serves `frontend/dist` alongside `/api`. A separate static host needs a same-origin `/api` reverse proxy to the backend. Hosting only the static files does not enable live inference.

No API keys, analytics, external fonts, or direct OpenRouter calls are bundled. Manrope is locally hosted under its included OFL license. The UI distinguishes actual live tool activity from saved replay, displays evaluation failures/errors, and never executes an eval from a public browser button.
