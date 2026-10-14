# Contributing

This repository is maintained by Databricks and intended for contributions from
Databricks Field Engineers. While the repository is public and meant to help
anyone developing solutions on Databricks, external contributions are not
currently accepted. Feel free to open an issue with requests, bug reports, or
suggestions — we read them.

## Development setup

### Local development

In production the frontend and the Flask API are served from one origin, so the
API client (`app/frontend/src/store/api.ts`) calls relative `/api` paths. Under
`yarn dev` Vite serves only static assets, so `vite.config.ts` **proxies `/api`
to a locally-running backend** (`http://127.0.0.1:8000` by default; override with
the `VITE_API_PROXY` env var). Run the backend alongside `yarn dev` to exercise
the whole stack locally.

The backend needs a Lakebase database. To avoid touching the shared production
data — and the app service principal's ownership of the production `waf` schema —
local development uses an **isolated `dev` branch** (declared in
[`app/databricks.yml`](app/databricks.yml)) with a **database you create and own**,
so migrations and writes work as your own identity with no extra grants.

```bash
export DATABRICKS_CONFIG_PROFILE=<your_profile>
# 1. Provision the dev branch (declared in the bundle; Lakebase creates its
#    `primary` endpoint). This deploys the whole bundle. Install it once with
#    deploy_notebook.py (README.md → "Deploying to Databricks"), as yourself;
#    after that you can redeploy from the CLI with the same values:
(cd app && databricks bundle deploy -t sandbox --profile $DATABRICKS_CONFIG_PROFILE \
  --var docs_catalog=<catalog> --var warehouse_id=<sql-warehouse-id>)

# 2. Look up the dev endpoint host and your identity
HOST=$(databricks postgres list-endpoints projects/waf-assessment-app/branches/dev \
  --profile $DATABRICKS_CONFIG_PROFILE -o json | jq -r '.[0].status.hosts.host')
EMAIL=$(databricks current-user me --profile $DATABRICKS_CONFIG_PROFILE -o json | jq -r '.userName')
TOKEN=$(databricks postgres generate-database-credential \
  projects/waf-assessment-app/branches/dev/endpoints/primary \
  --profile $DATABRICKS_CONFIG_PROFILE -o json | jq -r '.token')

# 3. One-time: create a database you own on the dev branch
PGPASSWORD=$TOKEN "$(brew --prefix libpq)/bin/psql" \
  "host=$HOST port=5432 dbname=postgres user=$EMAIL sslmode=require" \
  -c "CREATE DATABASE waf_dev;"

# 4. Run the backend against it (from app/backend/). Leaving DATABRICKS_APP_NAME
#    unset selects local mode, which mints Lakebase tokens via the CLI profile.
cd app/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PGHOST=$HOST
export PGUSER=$EMAIL
export PGPORT=5432
export PGDATABASE=waf_dev            # your own database, not the app's `waf`
export PGSCHEMA=public               # you own `public` in a database you created
export ENDPOINT_NAME=projects/waf-assessment-app/branches/dev/endpoints/primary
# Optional: enable document uploads (stored via your CLI profile)
# export DOCS_VOLUME_PATH=/Volumes/<docs_catalog>/waf_assessment/architecture_docs
flask --app app db upgrade           # applies migrations into waf_dev
python app.py                        # serves the API on :8000
```

Then run `(cd app/frontend && yarn dev)` in another terminal; the proxy forwards `/api` to the backend
and the full app works at http://localhost:5173. Point the backend at the
production branch instead only when you specifically need production data — but
note the app runs as your user there, not the service principal, so writes to the
production `waf` schema may be denied.

## Conventions

The essentials, enforced by `tsconfig.json` (strict) and `.eslintrc.cjs`:

- TypeScript only; named exports; `interface` for props
- Function components, never defined inside another component
- No `as` casts — narrow with type guards
- Emotion object styles using the tokens in `app/frontend/src/styles/theme.ts`; no hardcoded
  hex values
- Keep domain logic in `app/frontend/src/core/` as pure functions

[CLAUDE.md](CLAUDE.md) has the full detail, including two failure modes specific
to this project (Zustand selector stability and service-worker precaching).

## Making a change

1. Branch off `main`.
2. Make the change, following the conventions above and in [CLAUDE.md](CLAUDE.md).
3. Verify it (from `app/frontend/`):

   ```bash
   yarn typecheck
   yarn lint
   yarn build
   ```

4. Exercise the affected flow in the browser and confirm the console is clean.
5. Commit with a [Conventional Commit](#commit-messages) message (a `commit-msg`
   hook checks this locally once you've run `npm install` at the repo root).
6. Open a pull request:
   - Use a short, descriptive title (aim for under 70 characters).
   - Explain what changed and why.
   - Include before/after screenshots for any UI change.
   - Confirm the diff carries no secrets or customer data (see
     [Please don't commit](#please-dont-commit)).

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/). Each commit
message is `<type>(<optional scope>): <description>`, written in the imperative
mood, with the first line kept under ~70 characters.

Types used in this repo:

- `feat` — a new feature (bumps the **minor** version)
- `fix` — a bug fix (bumps the **patch** version)
- `docs` — documentation only
- `style` — formatting or whitespace, no change in behavior
- `refactor` — a code change that neither fixes a bug nor adds a feature
- `perf` — a performance improvement
- `test` — adding or correcting tests
- `build` — build system, dependencies, or bundling
- `ci` — CI configuration (`.github/workflows/`)
- `chore` — housekeeping that doesn't touch `src` or tests

A breaking change adds `!` after the type/scope (`feat!:`) or a
`BREAKING CHANGE:` footer, and bumps the **major** version. These types line up
with the version bumps in [Versioning and releases](#versioning-and-releases).

```
feat(results): add PDF export of the assessment report
fix(agents): correct question replication across categories
docs: document the conventional-commits convention
```

A [husky](https://typicode.github.io/husky/) `commit-msg` hook validates each
message against these rules via [commitlint](https://commitlint.js.org/). The
tooling is a small root-level `package.json` (repo-wide, separate from the
`app/frontend/` app package), so enable the hook once per clone with a single
install at the repo root:

```bash
npm install        # from the repo root — installs commitlint + husky and wires the hook
```

The hook rejects a non-conforming message locally. It is developer convenience,
not a gate: it can be skipped with `git commit --no-verify`, and only runs after
the install above. Treat the convention itself — not the hook — as the rule.

## Versioning and releases

The app version is a single number in `app/frontend/package.json`, mirrored by a
git tag `vX.Y.Z`. The tag marks the release version, but the GitHub Pages deploy
(`.github/workflows/deploy.yml`) is triggered by the merge into `main`, not by
the tag. The flow is `release/* → tag vX.Y.Z → merge to main → deploy`.

Treats `0.x.0` for a batch of features, reserve `x.0.0` for stable release and `0.0.x` for fixes.

To cut a release, from a `release/*` branch cut off `develop` (run the `yarn`
command from `app/frontend/`):

```bash
yarn version --new-version 0.2.0   # edits package.json and creates tag v0.2.0
git push && git push --tags        # push the release branch and the tag
```

Then open a PR from the `release/*` branch into `main`; merging it deploys the
docs site. Merge `main` back into `develop` afterwards so the version bump lands
on both.

`app/agents/pyproject.toml` is an internal, unpublished package; its version is
parked at `0.0.0` and is not maintained — don't bump it.

## Adding a WAF question

Questions are static data, not code. The question set in
`app/data/waf-data.json` is a three-level tree: an architecture-layer
**category** (Ingestion, Storage, Processing, Orchestration, Analytics, AI, ML)
contains every WAF **pillar**, and each pillar holds the **questions** worded for
that layer. Add a new entry to the right category → pillar with its `id`,
`principle`, `title`, and `details`; the category is simply where the question
lives in the tree. Optionally include Databricks guidance and a cloud-provider
note so the assessment can tailor advice to the selected provider.

After editing, run `yarn typecheck && yarn lint` and check the question renders
under the right category, pillar, and principle via `yarn dev`. The app is
English-only, so write the question text directly — there is no translation
layer to update.

## Adding a check (or a new layer agent)

A check is one module under `app/agents/waf_agents/<layer>/checks/`, decorated
with `@register(layer=..., question_ids=[...])`, implementing `collect` (gather
evidence) and `judge` (evidence → verdict). Import it in that package's
`__init__.py`. Because checks are keyed to question ids loaded from
`app/data/waf-data.json` at runtime, adding a question never breaks a run — it simply
awaits a check. A new layer agent is a `WafAgent` subclass decorated with
`@agent("<layer>")`; the factory finds it by layer id.

The checks have an offline test suite (no workspace needed). Run it from
`app/agents/`:

```bash
uv run --extra dev pytest        # run the suite
uv run --extra dev ruff check .  # lint
```

## Accessibility

Keep text contrast at WCAG AA (4.5:1) and make interactive elements reachable and
operable by keyboard. Prefer semantic HTML and `aria-*` attributes.

## Please don't commit

- Credentials, tokens, or API keys
- Customer data, PII, or anything from a real customer engagement
- Internal-only Databricks material

This is a public repository. Assessment content should be generic guidance, not
findings from a specific customer.

## Reporting bugs

Open a GitHub issue with what you expected, what happened, your browser, and the
steps to reproduce. Console output helps.

For security issues, follow [SECURITY.md](SECURITY.md) instead — do not open a
public issue.
