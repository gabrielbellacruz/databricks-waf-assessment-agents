# Databricks Well Architected Framework Assessment Tool

<div align="center">

[![Built on Databricks](https://img.shields.io/badge/Built_on-Databricks-FF3621?style=for-the-badge&logo=databricks&logoColor=white)](https://www.databricks.com/)
[![License](https://img.shields.io/badge/License-Databricks-1B3139?style=for-the-badge)](./LICENSE)

![React 18](https://img.shields.io/badge/React_18-61DAFB?style=flat-square&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Vite](https://img.shields.io/badge/Vite-646CFF?style=flat-square&logo=vite&logoColor=white)
![Emotion](https://img.shields.io/badge/Emotion-DB7093?style=flat-square)
![Zustand](https://img.shields.io/badge/Zustand-433E38?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-000000?style=flat-square&logo=flask&logoColor=white)
![Lakebase Postgres](https://img.shields.io/badge/Lakebase-Postgres-336791?style=flat-square&logo=postgresql&logoColor=white)
![uv](https://img.shields.io/badge/uv-managed-DE5FE9?style=flat-square&logo=python&logoColor=white)
![PWA](https://img.shields.io/badge/PWA-5A0FC8?style=flat-square&logo=pwa&logoColor=white)

</div>

A solution for running structured [Databricks Well Architected
Framework](https://docs.databricks.com/en/lakehouse-architecture/index.html)
(WAF) assessments.

Work across the seven pillars of the framework and score each one, with a
breakdown per architecture layer and per pillar.

## Demo

A short walkthrough — creating an assessment, answering questions, and reviewing
the score and backlog. Click to play:

[![Watch the WAF Assessment Tool demo](./docs/waf-tool-demo-poster.jpg)](./docs/waf-tool-demo.mp4)

## Running an assessment

1. Click **Start New Assessment**, then **New Assessment**
2. Name it, pick the categories that apply and set a cloud provider
3. Answer each question: *Answer later*, *Open*, *In Progress*, *Completed*, or
   *Ignore*
4. Open the **Results** tab for the score and pillar breakdown

Use the 📋 button in the header to switch between assessments, or to export one
as JSON and import it elsewhere.

![Assessment](./docs/assessment-example.png)

## Getting started

### Architecture

![High Level Architecture](./docs/Databricks%20Well%20Architected%20Framework%20Assessment%20Tool.gif)

### Prerequisites

**In your workspace**

- **Unity Catalog** and **serverless compute** enabled (the agents and the
  deploy notebook run on serverless). The notebook's compute needs internet
  access to GitHub and PyPI.
- **Databricks Apps** and **Lakebase** available. The bundle creates a Lakebase
  project named `waf-assessment-app` and an app named `waf-assessment`.
- A **model serving endpoint** for the assessment LLM. The default is the
  Foundation Model API endpoint `databricks-claude-opus-4-8`; check that it's
  listed under **Serving**.
- A **SQL warehouse** for the agents to run their system-table queries on
  (serverless recommended).
- An existing **Unity Catalog catalog** for uploaded architecture documents.
  The bundle creates the `waf_assessment` schema and `architecture_docs` volume
  inside it, but it doesn't create the catalog.

**People and permissions**

| Who | Needs | Used in |
| --- | ----- | ------- |
| The person deploying | Permission to create apps, Lakebase projects, and Jobs (a workspace admin is simplest). `CREATE SCHEMA` on the docs catalog, plus `MANAGE` on it unless all account users already have `USE CATALOG` there. The *Service Principal: User* role on the app's service principal, which the notebook grants you in step 2. | Steps 1–3 |
| A metastore admin | Enables system schemas and grants the app's service principal read access on them. | Step 4 |

### Deploying to Databricks

Everything is declared in one bundle, [`app/databricks.yml`](app/databricks.yml):
the app, its Lakebase database, the docs Volume, and the seven agent Jobs. You
supply two workspace-specific values, and the bundle wires up the rest.
Databricks creates the app's service principal, the Jobs run as it, and the
app's resources (docs Volume, SQL warehouse, model endpoint) grant it access.

You deploy it from a notebook in your workspace:

1. Go to **Workspace → Create → Git folder** and clone this repository.
2. Open [`deploy_notebook.py`](deploy_notebook.py) from the Git folder and attach
   serverless compute.
3. Click **Run all**. The first run stops at the settings cell and creates three
   widgets at the top. Fill them in, then click **Run all** again.

| Widget | Set it to |
| ------ | --------- |
| Catalog for uploaded docs | An existing catalog. The bundle creates the `waf_assessment` schema and `architecture_docs` volume inside it. |
| SQL warehouse | The warehouse the agents run their queries on. |
| Model serving endpoint | Any chat model endpoint. Defaults to `databricks-claude-opus-4-8`. |

The notebook downloads the Databricks CLI onto its compute and deploys the
bundle as you, in four steps:

1. **Validate** the configuration with your values.
2. **Create the app** and what it needs (Lakebase database, docs Volume), then
   grant you the *Service Principal: User* role on the app's service principal.
   The agent Jobs run as that principal, and setting a Job to run as a service
   principal requires this role, even for workspace admins. As the app's
   creator you're already its *Service Principal: Manager*, which allows the
   grant.
3. **Deploy the agent Jobs and start the app**, then print its URL.
4. **Grant the app read access to system tables**, which the agents answer
   questions from. This needs a metastore admin; if you aren't one, the
   notebook prints the SQL to hand to one.

The first run takes a few minutes, mostly creating the Lakebase project. Open
the URL and create an assessment. The app works right away; agent checks report
*Unknown* until step 4 is done.

Some checks also read job, pipeline, and cluster configuration through REST
APIs, and those APIs return only the objects the service principal can see. For
fuller results, give it *Can View* on the workloads you want assessed.

#### Updating an existing deployment

Pull the latest changes into the Git folder, then **Run all** again. Every step
is safe to re-run. Deploy as the same user each time: the deployment state lives
in that user's workspace folder.

#### Removing the deployment

From a machine with the Databricks CLI, as the user who deployed it, run
`databricks bundle destroy -t sandbox --var docs_catalog=<catalog> --var warehouse_id=<id>`
from the `app/` folder. This deletes everything the bundle created, including
the Lakebase project with every assessment in it, and the docs Volume with
every uploaded file.

#### Troubleshooting

| Symptom | Likely cause |
| ------- | ------------ |
| The notebook fails downloading the CLI or `uv` | Its compute has no internet access to GitHub or PyPI. Allow it, or attach a cluster that has access. |
| A deploy fails on the Jobs with `must have 'servicePrincipal.user' role` | Step 2 couldn't grant you the role, for example because someone else created the app. Ask them or an admin to grant you *Service Principal: User* on `app-… waf-assessment` (**Settings → Identity and access → Service principals → Permissions**), then **Run all** again. |
| A deploy fails creating the schema or the app's `docs-volume` resource | You lack `CREATE SCHEMA` on the docs catalog, or `MANAGE` on it (needed unless all account users have `USE CATALOG` there). |
| A deploy says the app `waf-assessment` already exists | An app with that name exists that this deployment doesn't manage, for example from an earlier install by another user. Delete it, or deploy as the user who created it. |
| An agent run fails with `Library installation failed` | The app publishes the agent code to the docs Volume (`_agents/`) when it starts. **Run all** again to restart it, then look for `[agent-wheel]` in the app's **Logs** tab. |
| Starting an agent does nothing | The app finds its Jobs by name (`waf-agent-<layer>`). Don't rename them. |
| Agent checks all come back *Unknown* | The system-table grants from step 4 are missing. Check the agent Job's run output for the failing query. |
| Backlog generation or LLM-judged checks fail | The model serving endpoint doesn't exist or isn't a chat model. |

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

To report a security issue, follow [SECURITY.md](SECURITY.md) rather than opening
a public issue.

## Roadmap

- [ ] WAF Genie Agent integration
- [ ] Embed historical AI/BI Dashboard
- [ ] External resource mapping and lineage

## Additional Assessments
- [SAT - Security Analysis Tool](https://github.com/databricks-industry-solutions/security-analysis-tool)
- [Ontology - Genie Ontology Readiness](https://github.com/databricks-solutions/genie-ontology-readiness/tree/main)
- [RC18 - Regulatory Data Governance](https://github.com/databricks-solutions/regulatory_data_governance)
- [Lakebridge - Facilitate migrations to Databricks](https://github.com/databrickslabs/lakebridge)
- [Forge - Use-case discovery](https://github.com/databricks-solutions/databricks-forge)

## License

Licensed under the [Databricks License](LICENSE). Built on top of and powered by the following open-source projects.

| Library | License |
| ------- | ------- |
| [React](https://github.com/facebook/react) | MIT |
| [Vite](https://github.com/vitejs/vite) | MIT |
| [TypeScript](https://github.com/microsoft/TypeScript) | Apache-2.0 |
| [Emotion](https://github.com/emotion-js/emotion) | MIT |
| [Zustand](https://github.com/pmndrs/zustand) | MIT |
| [Chart.js](https://github.com/chartjs/Chart.js) | MIT |
| [react-chartjs-2](https://github.com/reactchartjs/react-chartjs-2) | MIT |
| [vite-plugin-pwa](https://github.com/vite-pwa/vite-plugin-pwa) / [Workbox](https://github.com/GoogleChrome/workbox) | MIT |
| [Flask](https://github.com/pallets/flask) / [Flask-SQLAlchemy](https://github.com/pallets-eco/flask-sqlalchemy) / [Flask-Migrate](https://github.com/miguelgrinberg/flask-migrate) | BSD-3-Clause |
| [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) / [Alembic](https://github.com/sqlalchemy/alembic) | MIT |
| [Gunicorn](https://github.com/benoitc/gunicorn) | MIT |
| [psycopg2](https://github.com/psycopg/psycopg2) | LGPL-3.0 |
