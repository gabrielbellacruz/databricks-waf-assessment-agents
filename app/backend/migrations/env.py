import logging
import os
from logging.config import fileConfig

from alembic import context
from flask import current_app
from sqlalchemy import text

# Alembic Config object, providing access to values in alembic.ini.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")


def get_engine():
    try:
        # Flask-SQLAlchemy < 3 and Alembic < 1.9
        return current_app.extensions["migrate"].db.get_engine()
    except (TypeError, AttributeError):
        # Flask-SQLAlchemy >= 3
        return current_app.extensions["migrate"].db.engine


def get_engine_url():
    try:
        return get_engine().url.render_as_string(hide_password=False).replace("%", "%%")
    except AttributeError:
        return str(get_engine().url).replace("%", "%%")


# Provide the DB URL and target metadata from the Flask app.
config.set_main_option("sqlalchemy.url", get_engine_url())
target_db = current_app.extensions["migrate"].db


def get_metadata():
    if hasattr(target_db, "metadatas"):
        return target_db.metadatas[None]
    return target_db.metadata


def run_migrations_offline():
    """Run migrations in 'offline' mode (emit SQL to script output)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=get_metadata(), literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode (against a live connection)."""

    # Skip an empty autogenerate revision when nothing changed.
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, "autogenerate", False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info("No changes in schema detected.")

    conf_args = current_app.extensions["migrate"].configure_args
    if conf_args.get("process_revision_directives") is None:
        conf_args["process_revision_directives"] = process_revision_directives

    connectable = get_engine()

    # The app's service principal owns a dedicated schema rather than `public`
    # (which it cannot write to). Create it first so both the objects and
    # Alembic's version table land there. IF NOT EXISTS makes this idempotent
    # across deploys; the connecting SP becomes the owner.
    schema = os.environ.get("PGSCHEMA", "waf")
    with connectable.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.commit()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            version_table_schema=schema,
            **conf_args,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
