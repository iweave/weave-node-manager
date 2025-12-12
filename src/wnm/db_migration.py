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

from sqlalchemy import text


def get_alembic_config(db_url: str = None):
    """
    Get Alembic configuration.

    NOTE: Alembic imports are done inside this function to prevent automatic
    logging reconfiguration at module import time.

    Args:
        db_url: Database URL (if None, uses default from alembic.ini)

    Returns:
        Alembic Config object
    """
    # Import alembic here to prevent it from reconfiguring logging at module import time
    from alembic.config import Config

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

    # Disable Alembic's logging configuration to prevent it from resetting root logger
    config = Config(alembic_ini, ini_section="alembic", attributes={'configure_logger': False})

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


def get_head_revision(config) -> str | list[str]:
    """
    Get the HEAD revision from migration scripts.

    Args:
        config: Alembic Config object

    Returns:
        HEAD revision hash (str) or list of revision hashes if multiple heads
    """
    # Import here to prevent module-level logging reconfiguration
    from alembic.script import ScriptDirectory
    from alembic.util.exc import CommandError

    script = ScriptDirectory.from_config(config)
    try:
        return script.get_current_head()
    except CommandError as e:
        # Handle multiple heads case
        if "multiple heads" in str(e).lower():
            # Return all heads as a list
            return script.get_heads()
        raise


def has_pending_migrations(engine, db_url: str) -> tuple[bool, str | None, str | list[str]]:
    """
    Check if there are pending migrations.

    Args:
        engine: SQLAlchemy engine
        db_url: Database URL

    Returns:
        Tuple of (has_pending, current_revision, head_revision)
        Note: head_revision can be a list if there are multiple heads
    """
    config = get_alembic_config(db_url)
    current = get_current_revision(engine)
    head = get_head_revision(config)

    # If current is None, either:
    # 1. New database (no alembic_version table, no data) - will be auto-stamped
    # 2. Legacy database (no alembic_version table, has data) - needs migration
    if current is None:
        # Check if this is a legacy database with existing data
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM machine"))
                row_count = result.scalar()
                if row_count > 0:
                    # Legacy database - has pending migrations
                    return True, current, head
        except Exception:
            # If we can't check the machine table, assume it's a new database
            pass

        # New database - will be handled by auto-stamp
        return False, current, head

    # If head is a list (multiple heads), we always have pending migrations
    if isinstance(head, list):
        return True, current, head

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
    # Import here to prevent module-level logging reconfiguration
    from alembic import command

    # Save current logging level (Alembic reconfigures logging)
    root_logger = logging.getLogger()
    saved_level = root_logger.level

    config = get_alembic_config(db_url)
    command.stamp(config, revision)

    # Restore logging level after Alembic finishes
    root_logger.setLevel(saved_level)
    logging.info(f"Database stamped with revision: {revision}")


def run_migrations(engine, db_url: str):
    """
    Run all pending migrations.

    Args:
        engine: SQLAlchemy engine
        db_url: Database URL
    """
    # Import here to prevent module-level logging reconfiguration
    from alembic import command

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

        # Check if we have multiple heads (branched migrations)
        if isinstance(head, list):
            logging.error("INSTALLATION ERROR: CORRUPTED MIGRATION HISTORY")
            logging.error("=" * 70)
            logging.error("")
            logging.error("The migration history in this installation has multiple branches.")
            logging.error("This is a bug in the software installation, not your database.")
            logging.error("")
            logging.error("Multiple heads detected:")
            for h in head:
                logging.error(f"  - {h}")
            logging.error("")
            logging.error("Please report this issue at:")
            logging.error("  https://github.com/happybeing/weave-node-manager/issues")
            logging.error("")
            logging.error("If you're running from source, you may need to:")
            logging.error("  1. Pull the latest changes from the repository")
            logging.error("  2. Rebuild/reinstall the package")
            logging.error("  3. Remove the database and re-import the nodes")
        else:
            logging.error("DATABASE MIGRATION REQUIRED")
            logging.error("=" * 70)
            logging.error("")
            logging.error("Your database schema is out of date:")
            logging.error(f"  Current revision: {current or 'none (legacy database)'}")
            logging.error(f"  Required revision: {head}")
            logging.error("")
            logging.error("IMPORTANT: Backup your database before proceeding!")
            logging.error("")

            # Provide different instructions for legacy databases vs normal migrations
            if current is None:
                # Legacy database - needs stamping first
                logging.error("This appears to be a legacy database without migration tracking.")
                logging.error("Before running migrations, you must first identify which version")
                logging.error("your database corresponds to and stamp it.")
                logging.error("")
                logging.error("For a v0.2.0 database, run:")
                logging.error("  alembic stamp fa0ca0abff5c")
                logging.error("")
                logging.error("Then run migrations:")
                logging.error("  wnm --force_action wnm-db-migration --confirm")
                logging.error("")
                logging.error("If you're unsure of your database version, please ask for help at:")
                logging.error("  https://github.com/iweave/weave-node-manager/issues")
            else:
                # Normal migration - already tracked
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
    IMPORTANT: This will NOT stamp legacy databases (databases with existing data
    but no alembic_version table). Those require manual stamping or migration.

    Args:
        engine: SQLAlchemy engine
        db_url: Database URL
    """
    current = get_current_revision(engine)

    # Only stamp if alembic_version table doesn't exist
    if current is None:
        # Check if this is a legacy database (has data but no alembic_version table)
        # Legacy databases should not be auto-stamped
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM machine"))
                row_count = result.scalar()
                if row_count > 0:
                    # This is a legacy database with data, don't auto-stamp
                    logging.debug("Legacy database detected (has data but no alembic_version), skipping auto-stamp")
                    return
        except Exception as e:
            # If we can't check the machine table, assume it's not a legacy database
            logging.debug(f"Could not check for legacy database: {e}")
            pass

        # Skip stamping for relative paths (./colony.db) or when alembic.ini not found
        # Stamping will fail for relative paths during module import
        try:
            # Check if we can find alembic.ini before attempting stamp
            current_dir = Path(__file__).parent
            alembic_ini_paths = [
                current_dir.parent.parent.parent / "alembic.ini",
                current_dir.parent.parent / "alembic.ini",
                Path("alembic.ini"),
            ]

            alembic_ini = None
            for path in alembic_ini_paths:
                if path.exists():
                    alembic_ini = str(path)
                    break

            if not alembic_ini:
                # Can't find alembic.ini, skip stamping silently
                return

            # Save logging level BEFORE calling functions that import alembic
            # (Alembic imports trigger logging reconfiguration)
            root_logger = logging.getLogger()
            saved_level = root_logger.level

            try:
                stamp_database(engine, db_url, "head")
                logging.info("New database auto-stamped with current migration version")
            except Exception:
                # Silently ignore stamping errors for new databases
                # This can happen with relative paths or missing alembic.ini
                pass
            finally:
                # Always restore logging level, even if there's an exception
                root_logger.setLevel(saved_level)
        except Exception:
            # Silently ignore other errors (e.g., checking alembic.ini existence)
            pass
