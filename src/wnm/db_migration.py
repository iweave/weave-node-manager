"""
Database migration detection and management using Alembic.

This module provides utilities to:
1. Detect if database migrations are pending
2. Run migrations programmatically
3. Auto-stamp new databases with current version
"""

import logging
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text


def get_alembic_config(db_url: str = None) -> Config:
    """
    Get Alembic configuration.

    Args:
        db_url: Database URL (if None, uses default from alembic.ini)

    Returns:
        Alembic Config object
    """
    # Find alembic.ini - it should be at the project root
    # When installed, it will be in the package root
    current_dir = Path(__file__).parent
    alembic_ini_paths = [
        current_dir.parent.parent.parent / "alembic.ini",  # Development
        current_dir.parent.parent / "alembic.ini",  # Installed package
        Path("alembic.ini"),  # Current directory
    ]

    alembic_ini = None
    for path in alembic_ini_paths:
        if path.exists():
            alembic_ini = str(path)
            break

    if not alembic_ini:
        raise FileNotFoundError(
            "Could not find alembic.ini. Database migrations cannot be managed."
        )

    config = Config(alembic_ini)

    # Override database URL if provided
    if db_url:
        config.set_main_option("sqlalchemy.url", db_url)

    return config


def get_current_revision(engine) -> str | None:
    """
    Get the current database revision from alembic_version table.

    Args:
        engine: SQLAlchemy engine

    Returns:
        Current revision hash, or None if table doesn't exist
    """
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
            return row[0] if row else None
    except Exception:
        # Table doesn't exist (new database or legacy database)
        return None


def get_head_revision(config: Config) -> str:
    """
    Get the HEAD revision from migration scripts.

    Args:
        config: Alembic Config object

    Returns:
        HEAD revision hash
    """
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()


def has_pending_migrations(engine, db_url: str) -> tuple[bool, str | None, str]:
    """
    Check if there are pending migrations.

    Args:
        engine: SQLAlchemy engine
        db_url: Database URL

    Returns:
        Tuple of (has_pending, current_revision, head_revision)
    """
    config = get_alembic_config(db_url)
    current = get_current_revision(engine)
    head = get_head_revision(config)

    # If current is None, either:
    # 1. New database (no alembic_version table)
    # 2. Legacy database (needs stamping)
    if current is None:
        return False, current, head  # Will be handled by auto-stamp

    # If current != head, we have pending migrations
    return current != head, current, head


def stamp_database(engine, db_url: str, revision: str = "head"):
    """
    Stamp the database with a specific revision without running migrations.

    This is used for:
    1. New databases created by Base.metadata.create_all()
    2. Legacy databases that need to be brought into the migration system

    Args:
        engine: SQLAlchemy engine
        db_url: Database URL
        revision: Revision to stamp (default: "head")
    """
    config = get_alembic_config(db_url)
    command.stamp(config, revision)
    logging.info(f"Database stamped with revision: {revision}")


def run_migrations(engine, db_url: str):
    """
    Run all pending migrations.

    Args:
        engine: SQLAlchemy engine
        db_url: Database URL
    """
    config = get_alembic_config(db_url)
    current = get_current_revision(engine)
    head = get_head_revision(config)

    logging.info(f"Running migrations from {current} to {head}")
    command.upgrade(config, "head")
    logging.info("Migrations completed successfully")


def check_and_warn_migrations(engine, db_url: str):
    """
    Check for pending migrations and exit with warning if found.

    This function should be called on startup (except when running migrations).
    If pending migrations are detected, it will:
    1. Print a warning message
    2. Tell user to backup database
    3. Exit with status code 1

    Args:
        engine: SQLAlchemy engine
        db_url: Database URL
    """
    pending, current, head = has_pending_migrations(engine, db_url)

    if pending:
        logging.error("=" * 70)
        logging.error("DATABASE MIGRATION REQUIRED")
        logging.error("=" * 70)
        logging.error("")
        logging.error("Your database schema is out of date:")
        logging.error(f"  Current revision: {current or 'none (legacy database)'}")
        logging.error(f"  Required revision: {head}")
        logging.error("")
        logging.error("IMPORTANT: Backup your database before proceeding!")
        logging.error("")
        logging.error("To run migrations:")
        logging.error("  wnm --force_action wnm-db-migration --confirm")
        logging.error("")
        logging.error("To backup your database:")
        if "sqlite:///" in db_url:
            db_path = db_url.replace("sqlite:///", "")
            logging.error(f"  cp {db_path} {db_path}.backup")
        else:
            logging.error(f"  cp {db_url} {db_url}.backup")
        logging.error("=" * 70)
        sys.exit(1)


def auto_stamp_new_database(engine, db_url: str):
    """
    Auto-stamp a new database with the HEAD revision.

    This should be called after Base.metadata.create_all() for new databases.

    Args:
        engine: SQLAlchemy engine
        db_url: Database URL
    """
    current = get_current_revision(engine)

    # Only stamp if alembic_version table doesn't exist
    if current is None:
        try:
            stamp_database(engine, db_url, "head")
            logging.info("New database auto-stamped with current migration version")
        except Exception as e:
            logging.warning(f"Could not auto-stamp database: {e}")
