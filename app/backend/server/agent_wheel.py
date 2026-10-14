"""Publish the agent wheel to the docs Volume, where the agent Jobs install it.

The agent Jobs run as this app's service principal, which can't read the
deployer's bundle folder that `bundle deploy` would upload the wheel to. So the
bundle ships the wheel inside the app source (backend/agents_dist/, filled by
the waf_agents artifact build) and the app copies it into its own Volume on
every start; the Jobs' environment installs it from there
(resources/agent_jobs.yml). The app SP can write that Volume through its
`docs-volume` resource, and publishing at start keeps the Jobs on the agent
code that shipped with the running app.

Runs once per container start, before gunicorn forks (backend/app.yaml).
"""

import glob
import os

from server import volumes

AGENT_WHEEL_DIR = "_agents"


def publish() -> str | None:
    """Upload the bundled wheel; returns its Volume path, or None when there is
    no Volume configured or no wheel shipped (e.g. local dev)."""
    root = volumes.volume_root()
    if root is None:
        return None
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    wheels = sorted(glob.glob(os.path.join(backend_dir, "agents_dist", "*.whl")))
    if not wheels:
        return None
    src = wheels[-1]
    dest = f"{root}/{AGENT_WHEEL_DIR}/{os.path.basename(src)}"
    with open(src, "rb") as f:
        volumes.upload(dest, f.read())
    return dest


if __name__ == "__main__":
    # Never block the app from starting: without the wheel only agent runs fail.
    try:
        published = publish()
        print(f"[agent-wheel] published {published or 'nothing'}", flush=True)
    except Exception as exc:
        print(f"[agent-wheel] FAILED: {exc}", flush=True)
