# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy the WAF Assessment Tool
# MAGIC
# MAGIC This notebook runs the README's **Deploying to Databricks** steps from inside your workspace.
# MAGIC It downloads the Databricks CLI onto this notebook's compute and deploys the bundle in `app/`
# MAGIC as you. Use **Run all** for the first install and again for every update: each step is safe
# MAGIC to re-run.
# MAGIC
# MAGIC **Before you start**
# MAGIC
# MAGIC - Open this notebook from a **Git folder** of the repository (**Workspace → Create → Git
# MAGIC   folder**), so the `app/` folder sits next to it.
# MAGIC - Attach **serverless** compute, or a cluster on Databricks Runtime 15.4 LTS or above. It needs
# MAGIC   internet access to download the CLI from GitHub and Python packages from PyPI.
# MAGIC - You need permission to create apps, Lakebase projects, and Jobs (a workspace admin is
# MAGIC   simplest), plus `CREATE SCHEMA` and `MANAGE` on the catalog you pick below.
# MAGIC - Always deploy as the same user. The deployment state lives in that user's workspace folder,
# MAGIC   whether you deploy from here or from the CLI on your machine.
# MAGIC
# MAGIC Step 4 also needs a **metastore admin**. If you aren't one, the notebook prints the SQL to
# MAGIC hand to them.

# COMMAND ----------

# MAGIC %pip install -q uv

# COMMAND ----------

# MAGIC %md
# MAGIC ## Settings
# MAGIC
# MAGIC Pick the values in the widgets at the top of the notebook, then **Run all** again.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

catalogs = sorted(
    c.name for c in w.catalogs.list() if c.catalog_type and c.catalog_type.value == "MANAGED_CATALOG"
)
warehouses = [f"{wh.id} · {wh.name}" for wh in w.warehouses.list()]

dbutils.widgets.combobox("docs_catalog", "", [""] + catalogs, "1. Catalog for uploaded docs")
dbutils.widgets.combobox("warehouse", "", [""] + warehouses, "2. SQL warehouse")
dbutils.widgets.text("assessment_model", "databricks-claude-opus-4-8", "3. Model serving endpoint")

DOCS_CATALOG = dbutils.widgets.get("docs_catalog").strip()
WAREHOUSE_ID = dbutils.widgets.get("warehouse").split(" ")[0].strip()
ASSESSMENT_MODEL = dbutils.widgets.get("assessment_model").strip()

if not (DOCS_CATALOG and WAREHOUSE_ID and ASSESSMENT_MODEL):
    raise ValueError("Pick a catalog and a SQL warehouse in the widgets at the top, then Run all again.")
print(f"catalog={DOCS_CATALOG}  warehouse={WAREHOUSE_ID}  model={ASSESSMENT_MODEL}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup
# MAGIC
# MAGIC Downloads the CLI and copies the bundle to the notebook's local disk, so the deploy's build
# MAGIC output never lands in your Git folder.

# COMMAND ----------

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile

CLI_VERSION = "1.20.0"  # the version this flow was validated with
TARGET = "sandbox"
APP_NAME = "waf-assessment"

# This notebook sits at the root of the Git folder; the bundle is in app/.
notebook_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
repo_root = os.path.dirname(notebook_path)
if not repo_root.startswith("/Workspace"):
    repo_root = "/Workspace" + repo_root
bundle_src = os.path.join(repo_root, "app")
if not os.path.exists(os.path.join(bundle_src, "databricks.yml")):
    raise FileNotFoundError(f"No bundle at {bundle_src}. Open this notebook from the repository's Git folder.")

WORK_DIR = "/tmp/waf-deploy"
BUNDLE_DIR = os.path.join(WORK_DIR, "app")
shutil.rmtree(WORK_DIR, ignore_errors=True)
shutil.copytree(
    bundle_src,
    BUNDLE_DIR,
    ignore=shutil.ignore_patterns(".databricks", "node_modules", "__pycache__", ".venv", "dist", "agents_dist"),
)

arch = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}[platform.machine()]
CLI = f"/tmp/databricks-cli-{CLI_VERSION}/databricks"
if not os.path.exists(CLI):
    url = (
        f"https://github.com/databricks/cli/releases/download/v{CLI_VERSION}/"
        f"databricks_cli_{CLI_VERSION}_linux_{arch}.zip"
    )
    archive, _ = urllib.request.urlretrieve(url)
    with zipfile.ZipFile(archive) as z:
        z.extractall(os.path.dirname(CLI))
    os.chmod(CLI, 0o755)

# The bundle's artifact build runs `uv build`, so uv (installed above) must be on PATH.
uv = shutil.which("uv", path=os.path.dirname(sys.executable)) or shutil.which("uv")
if not uv:
    raise RuntimeError("uv isn't installed. Run the %pip cell at the top again.")
UV_DIR = os.path.dirname(uv)


def cli_env() -> dict:
    """Environment for the CLI: authenticated as you, with this notebook's token."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("DATABRICKS_")}
    token = w.config.authenticate()["Authorization"].split(" ", 1)[1]
    env.update(DATABRICKS_HOST=w.config.host, DATABRICKS_TOKEN=token, DATABRICKS_AUTH_TYPE="pat")
    env["PATH"] = UV_DIR + os.pathsep + env.get("PATH", "")
    return env


def cli(*args: str) -> None:
    """Run a CLI command from the bundle folder, streaming its output."""
    print("$ databricks " + " ".join(args), flush=True)
    proc = subprocess.Popen(
        [CLI, *args], cwd=BUNDLE_DIR, env=cli_env(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    for line in proc.stdout:
        print(line, end="", flush=True)
    if proc.wait() != 0:
        raise RuntimeError(f"`databricks {' '.join(args[:2])}` failed - see the output above.")


def app_info() -> dict:
    """The app's details, over REST: the runtime's preinstalled SDK may predate `w.apps`."""
    return w.api_client.do("GET", f"/api/2.0/apps/{APP_NAME}")


BUNDLE_ARGS = [
    "-t", TARGET,
    "--var", f"docs_catalog={DOCS_CATALOG}",
    "--var", f"warehouse_id={WAREHOUSE_ID}",
    "--var", f"assessment_model={ASSESSMENT_MODEL}",
]
cli("--version")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1. Validate the configuration

# COMMAND ----------

cli("bundle", "validate", *BUNDLE_ARGS)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2. Create the app and allow yourself to run Jobs as it
# MAGIC
# MAGIC The agent Jobs run as the app's service principal, which Databricks creates together with
# MAGIC the app. Setting a Job to run as a service principal requires the *Service Principal: User*
# MAGIC role on it, even for workspace admins. So this step creates only the app and what it needs
# MAGIC (Lakebase database, docs Volume), then grants you that role. As the app's creator you are
# MAGIC already *Service Principal: Manager* on it, which allows the grant. The first run takes a
# MAGIC few minutes, mostly creating the Lakebase project.

# COMMAND ----------

cli("bundle", "deploy", "--select", "apps.waf_assessment", *BUNDLE_ARGS)

app_sp = app_info()["service_principal_client_id"]
me = f"users/{w.current_user.me().user_name}"
host_metadata = json.load(urllib.request.urlopen(f"{w.config.host}/.well-known/databricks-config"))
rule_set_name = f"accounts/{host_metadata['account_id']}/servicePrincipals/{app_sp}/ruleSets/default"
RULE_SETS = "/api/2.0/preview/accounts/access-control/rule-sets"
USER_ROLE = "roles/servicePrincipal.user"

rule_set = w.api_client.do("GET", RULE_SETS, query={"name": rule_set_name, "etag": ""})
rules = rule_set.get("grant_rules", [])
user_rule = next((r for r in rules if r["role"] == USER_ROLE), None)
if user_rule and me in user_rule.get("principals", []):
    print(f"You already have Service Principal: User on {app_sp}.")
else:
    if user_rule:
        user_rule["principals"].append(me)
    else:
        rules.append({"role": USER_ROLE, "principals": [me]})
    # The rule set is replaced as a whole, so this sends the current rules plus yours.
    w.api_client.do("PUT", RULE_SETS, body={
        "name": rule_set_name,
        "rule_set": {"name": rule_set_name, "etag": rule_set["etag"], "grant_rules": rules},
    })
    print(f"Granted you Service Principal: User on {app_sp}.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3. Deploy everything and start the app
# MAGIC
# MAGIC Creates the agent Jobs, then starts the app on the deployed version. Starting the app also
# MAGIC hands the agent code to the Jobs, so updates take effect here.

# COMMAND ----------

cli("bundle", "deploy", *BUNDLE_ARGS)
cli("bundle", "run", "waf_assessment", *BUNDLE_ARGS)

app_url = app_info()["url"]
displayHTML(f'<p>The app is running: <a href="{app_url}" target="_blank">{app_url}</a></p>')

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4. Give the app read access to system tables
# MAGIC
# MAGIC The agents answer questions from system tables. A bundle can't grant access to the `system`
# MAGIC catalog, so this step does it directly, which needs a **metastore admin**. If you aren't one,
# MAGIC it prints the SQL to hand to an admin. The app works without this step, but agent checks
# MAGIC report *Unknown* until it's done.

# COMMAND ----------

SYSTEM_SCHEMAS = ["access", "compute", "query", "lakeflow", "serving", "ai_gateway"]
metastore_id = w.metastores.current().metastore_id
for schema in SYSTEM_SCHEMAS:
    try:
        w.api_client.do("PUT", f"/api/2.1/unity-catalog/metastores/{metastore_id}/systemschemas/{schema}")
        print(f"enabled system.{schema}")
    except Exception as exc:  # already enabled, or not an admin
        print(f"system.{schema}: {str(exc).split(' Config:')[0].splitlines()[0]}")

grants = [f"GRANT USE CATALOG ON CATALOG system TO `{app_sp}`"] + [
    f"GRANT USE SCHEMA, SELECT ON SCHEMA system.{schema} TO `{app_sp}`"
    for schema in ["information_schema", "billing", *SYSTEM_SCHEMAS]
]
missing = []
for statement in grants:
    try:
        spark.sql(statement)
    except Exception:
        missing.append(statement)

if missing:
    print("\nYou can't grant these yourself. Ask a metastore admin to run:\n")
    print(";\n".join(missing) + ";")
else:
    print(f"\nSystem-table access granted to the app's service principal ({app_sp}).")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Done
# MAGIC
# MAGIC Open the app from the link in step 3, create an assessment, and run an agent on one layer.
# MAGIC
# MAGIC - **Updating:** pull the latest changes into the Git folder, then **Run all** again.
# MAGIC - **Logs:** the app's **Logs** tab under **Compute → Apps → waf-assessment**, and each agent
# MAGIC   Job's run output under **Jobs & Pipelines**.
# MAGIC - **Troubleshooting:** see the README's **Troubleshooting** table.
