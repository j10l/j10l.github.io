# AGENTS.md

## Cursor Cloud specific instructions

This repo is a **single static Next.js site** (App Router) — the personal/portfolio site for Joeran Kinzel. There is **no backend, database, or external service**. It builds to static HTML via `output: "export"` (see `next.config.ts`) and deploys to GitHub Pages (`.github/workflows/deploy.yml`).

Node 22 (matches CI). Package manager is **npm** (`package-lock.json` present). Standard scripts live in `package.json`:

- `npm run dev` — Next.js dev server on `http://localhost:3000` (the only service to run for local/E2E testing).
- `npm run lint` — ESLint.
- `npm run build` — static production build; emits `out/`.

Non-obvious notes:

- The repo root contains **legacy "Monospace Web" template remnants** (`index.md`, `template.html`, `Makefile`, `flake.nix`, `index.js`, `index.css`, `reset.css`). These are a Pandoc/Nix/`live-server` pipeline that is **not part of the Next.js product** — ignore them for development; you do not need pandoc or Nix.
- `next.config.ts` uses `output: "export"` with `images.unoptimized: true`, so `next/image` serves static unoptimized assets from `/public/images`.
