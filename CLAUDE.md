# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A full-stack tool for running Databricks Well Architected Framework assessments,
deployed as a Databricks App. The frontend is a React 18 + TypeScript + Vite PWA
styled with Emotion, state in Zustand. The questions are static JSON in
the canonical `app/data/`; assessments are persisted server-side in Lakebase (Postgres) via
a Flask backend and shared org-wide. The compiled frontend is served by that
same backend from `app/backend/static/`.

The whole deployable unit lives under `app/` (its Databricks Asset Bundle is
`app/databricks.yml`). Each architecture layer can also have an **agent** that
answers that layer's questions automatically from workspace signals — see
**Agents** below.

The question set is a three-level tree: an architecture-step **category**
(Ingestion, Storage, Processing, Orchestration, Analytics, AI, ML) contains
every WAF **pillar**, and each pillar holds the **questions** reworded for that
step. Every pillar is evaluated within every category. An assessment's
`categories` field selects which architecture layers are in scope. Answers are
keyed `categoryId -> pillarId -> questionId -> status`.

## Commands

The frontend is a self-contained package under `app/frontend/`; run all `yarn`
commands from there (`cd app/frontend` first).

```bash
yarn dev          # dev server with hot reload
yarn typecheck    # tsc --noEmit
yarn lint         # eslint
yarn build        # typecheck, then build to app/frontend/dist/
yarn preview      # serve the production build
```

Run `yarn typecheck && yarn lint` (from `app/frontend/`) before saying a change is done.

The agent (Python) commands run from `app/agents/` — see **Agents**.

## Layout

```
app/                         the deployable unit; its bundle is app/databricks.yml
app/data/                    canonical WAF question tree (JSON) — read by the agents;
                             copied to app/frontend/public/data at build (git-ignored copy)
app/frontend/                self-contained Vite app (package.json, vite/ts config)
app/frontend/src/core/       domain logic — pure functions, no React, no DOM
app/frontend/src/store/      Zustand store + API client (persists to Lakebase)
app/frontend/src/hooks/      React hooks (e.g. useAgentFindings)
app/frontend/src/types/      domain types
app/frontend/src/styles/     design tokens (theme.ts) and global styles
app/frontend/src/components/ ui/ primitives, layout/, assessments/ modals
app/frontend/src/pages/      home/, assessment/, results/
app/backend/                 Flask backend: serves the built frontend + /api, Lakebase
app/backend/server/          routes, models, db/config; agents.py triggers the agent jobs
app/backend/migrations/      Alembic revisions
app/backend/static/          compiled frontend (git-ignored; `mv app/frontend/dist app/backend/static`)
app/agents/                  uv-managed waf_agents package: the per-layer WAF agents
app/agents/waf_agents/       core/ (WafAgent + registry) plus one subpackage per layer,
                             each with agent.py and a checks/ directory
app/resources/               DAB job definitions (agent_jobs.yml — one job per layer)
```

Import with the `@/` alias, not long relative paths.

Put logic in `app/frontend/src/core/` as pure functions where you can — it is the easiest
part to reason about and change. Components render; they don't compute.

## Conventions

Enforced by `tsconfig.json` (strict) and `.eslintrc.cjs`:

- TypeScript only. No `.js` source files.
- Named exports. No `export default` (except `vite.config.ts`).
- `interface` for props, always exported.
- Function components. No classes.
- No components defined inside components — extract and pass props.
- No `as` casts. Narrow with type guards; see `app/frontend/src/core/assessmentFile.ts`
  for how untrusted input is validated.

## Styling

Emotion object styles at module scope, applied with the `css` prop:

```tsx
const cardCss = css({ display: 'flex', gap: spacing.sm });
export const Thing = () => <div css={cardCss}>…</div>;
```

Use tokens from `app/frontend/src/styles/theme.ts`. Never hardcode a hex value — there are
currently zero outside that file, and it should stay that way. Add missing
values to the theme instead.

Surfaces are flat colors. There are no gradient tokens on purpose.

## Two things that will bite you

**Zustand selectors must return a stable reference.** Sorting or mapping inside
a selector creates a new array every call and React throws
"Maximum update depth exceeded", leaving a blank page. Select the raw slice and
derive with `useMemo` — see `useAssessmentsByRecent`.

**Every asset must be precached exactly once.** In `vite.config.ts`, manifest
icons are precached by the plugin, so `globPatterns` deliberately excludes
`png`; other images go in `includeAssets`. A file listed twice makes Workbox
throw while the service worker evaluates, so it never registers and offline
support silently disappears while the app still works online.

## Agents

Each architecture layer can have an **agent** that answers that layer's WAF
questions from workspace signals (system tables, Unity Catalog metadata, job and
pipeline config) and writes findings back to the assessment. Agents live in
`app/agents/` as the `uv`-managed `waf_agents` package and run as serverless
Databricks Jobs (`app/resources/agent_jobs.yml`, one per layer); the Flask
backend triggers them via `app/backend/server/agents.py`.

- A **layer agent** is a `WafAgent` subclass decorated `@agent("<layer>")`, at
  `app/agents/waf_agents/<layer>/agent.py`; the factory finds it by layer id.
- A **check** is one module under `app/agents/waf_agents/<layer>/checks/`,
  decorated `@register(layer=..., question_ids=[...])`, implementing `collect`
  (gather evidence) and `judge` (evidence → verdict). Import it in that package's
  `__init__.py`. Checks are keyed to question ids from `app/data/waf-data.json`,
  so adding a question never breaks a run — it simply awaits a check.
- Tests are offline (no workspace). From `app/agents/`:
  `uv run --extra dev pytest` and `uv run --extra dev ruff check .`.

Separately, a **results-level backlog agent** turns a whole assessment into a
prioritized implementation backlog. Unlike the layer agents it needs no workspace
access, so it is **not** a Job: the Flask backend (`app/backend/server/backlog.py`)
prompts the same serving endpoint over REST in a background thread and stores the
tasks on a `backlog_runs` row. It's triggered on demand from the Results page
(`POST /assessments/<id>/backlog/run`, polled via `GET …/backlog`) and shown on the
page and in the exported PDF. Like the layer agents it only runs in the deployed App.

## Accessibility

Aim for WCAG AA (4.5:1) on text. Note that white on Lava 600 is only 3.62:1, so
check contrast before introducing a new color pairing rather than assuming brand
colors are safe.

Prefer semantic HTML and real `aria-*` attributes over `data-testid` hooks.

## Content changes

- **New question** → `app/data/waf-data.json` (canonical; the build copies it into
  `app/frontend/public/data/`), under the right category →
  pillar in the tree. A question's category is where it lives in the tree; there
  is no separate mapping file.
- **UI text** → write it inline in the component. The app is English-only;
  there is no translation layer.

Reusable copy that isn't inline lives next to what it describes:
`PILLAR_SUMMARIES` and `DOC_RESOURCES` in `app/frontend/src/pages/home/pillarContent.ts`,
`STATUS_DEFINITIONS` in `app/frontend/src/core/status.ts`, `MATURITY_LABELS` in
`app/frontend/src/core/scoring.ts`.

## Project site (GitHub Pages)

The public landing page is a single self-contained `docs/index.html` (inline CSS,
no build step, theme-aware). `.github/workflows/deploy.yml` publishes the `docs/`
folder to GitHub Pages on tag pushes (and manual `workflow_dispatch`). Keep the
page's copy in sync with the app whenever the thing it describes changes, and keep
links pointing at the canonical repo. In particular, update `docs/index.html` when:

- **Pillars, layers, or the feature list** change.
- **Scoring changes** — the status→points table and the "How it's measured" copy
  must match `core/status.ts` (`STATUS_DEFINITIONS`, `MAX_QUESTION_SCORE`) and
  `core/scoring.ts` (the rollup and percentage formulas).
- **Question counts change** — the hero stats (`7 × 7`, `245` questions,
  `5` questions per pillar, the 15 / 105 / 735 maxima) are derived from
  `app/data/waf-data.json`; recompute them if the tree grows or shrinks.
- **Agent behavior changes** — the verdict→status mapping (Met→Completed,
  Partial→In Progress, Not met→Open, Unknown→needs review) must match
  `VERDICT_STATUS` in `core/status.ts`.

## Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):
`<type>(<scope>): <description>`, imperative mood, first line under ~70 chars.
Types in use: `feat` (→ minor), `fix` (→ patch), `docs`, `style`, `refactor`,
`perf`, `test`, `build`, `ci`, `chore`. A breaking change uses `type!:` or a
`BREAKING CHANGE:` footer (→ major). These types line up with the version bumps
under **Versioning** below. See CONTRIBUTING.md for the full list and examples.

A root-level `package.json` (repo-wide dev tooling only — **not** the app
package) carries a husky `commit-msg` hook that validates messages with
commitlint (`commitlint.config.cjs`). Run `npm install` at the repo root once to
enable it; it's local convenience, bypassable with `--no-verify`.

## Versioning

The app version lives in **one** place: `app/frontend/package.json`. The git tag
`vX.Y.Z` mirrors it, and pushing a tag triggers the GitHub Pages deploy
(`.github/workflows/deploy.yml`) — so a tag is the release marker. Bump from
`app/frontend/` with `yarn version --new-version X.Y.Z`, which edits
`package.json` and creates the matching tag.

- Reserve
  `x.0.0` for stable release. Bump the **minor** for a batch of
  features, the **patch** for fixes.
- `app/agents/pyproject.toml` is an internal, unpublished package — its version is
  parked at `0.0.0` and is **not** the source of truth. Don't bump it.
- The root `package.json` (commit-lint tooling) is likewise parked at `0.0.0` and
  is not a version source. Don't bump it.

See CONTRIBUTING.md for the release steps.

## Publishing

This repo is customer-facing. Don't commit credentials, customer data, or
internal-only material. The disclaimer in `README.md` and the `LICENSE` are
required — leave them in place.

## Keeping this file accurate

This file is loaded into context every session, so stale guidance is worse than
none. Update it when directories move, the stack changes, a command or workflow
changes, or a durable convention or footgun emerges. Don't update it for
in-flight work, one-off bug fixes, or refactors that don't move files. Keep it to
one root `CLAUDE.md` — no nested per-directory copies.
