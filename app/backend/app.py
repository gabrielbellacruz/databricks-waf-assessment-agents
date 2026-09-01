"""Entrypoint. `app` is consumed by both gunicorn (`gunicorn app:app`) and the
Flask CLI (`flask --app app db upgrade`)."""

from server import create_app

app = create_app()

if __name__ == "__main__":
    import os

    port = int(os.environ.get("DATABRICKS_APP_PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
