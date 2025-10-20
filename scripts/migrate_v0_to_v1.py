#!/usr/bin/env python3
"""
Migration script: WNM v0.0.9 → v1.0

This script migrates the database schema from UpperCamelCase to snake_case
and adds new fields for container support and process manager abstraction.

WARNING: This is a breaking change. Backup your colony.db before running!

Usage:
    python3 scripts/migrate_v0_to_v1.py [--db-path /path/to/colony.db]
"""

import argparse
import logging
import shutil
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Default delay conversion: minutes to seconds
MINUTES_TO_SECONDS = 60


def backup_database(db_path: Path) -> Path:
    """Create a backup of the database before migration"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_suffix(f".backup_{timestamp}.db")
    logger.info(f"Creating backup: {backup_path}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def migrate_machine_table(conn: sqlite3.Connection) -> None:
    """Migrate Machine table from UpperCamelCase to snake_case"""
    logger.info("Migrating Machine table...")

    cursor = conn.cursor()

    # Create new machine table with snake_case fields
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS machine_new (
            id INTEGER PRIMARY KEY,
            cpu_count INTEGER,
            node_cap INTEGER,
            cpu_less_than INTEGER,
            cpu_remove INTEGER,
            mem_less_than INTEGER,
            mem_remove INTEGER,
            hd_less_than INTEGER,
            hd_remove INTEGER,
            delay_start INTEGER,
            delay_upgrade INTEGER,
            delay_remove INTEGER,
            node_storage TEXT,
            rewards_address TEXT,
            donate_address TEXT,
            max_load_average_allowed REAL,
            desired_load_average REAL,
            port_start INTEGER,
            hdio_read_less_than INTEGER,
            hdio_read_remove INTEGER,
            hdio_write_less_than INTEGER,
            hdio_write_remove INTEGER,
            netio_read_less_than INTEGER,
            netio_read_remove INTEGER,
            netio_write_less_than INTEGER,
            netio_write_remove INTEGER,
            last_stopped_at INTEGER,
            host TEXT,
            crisis_bytes INTEGER,
            metrics_port_start INTEGER,
            environment TEXT,
            start_args TEXT,
            max_concurrent_upgrades INTEGER DEFAULT 1,
            max_concurrent_starts INTEGER DEFAULT 2,
            max_concurrent_removals INTEGER DEFAULT 1,
            node_removal_strategy TEXT DEFAULT 'youngest'
        )
    """)

    # Migrate data, converting field names and delay times from minutes to seconds
    cursor.execute("""
        INSERT INTO machine_new (
            id, cpu_count, node_cap, cpu_less_than, cpu_remove,
            mem_less_than, mem_remove, hd_less_than, hd_remove,
            delay_start, delay_upgrade, delay_remove,
            node_storage, rewards_address, donate_address,
            max_load_average_allowed, desired_load_average,
            port_start, hdio_read_less_than, hdio_read_remove,
            hdio_write_less_than, hdio_write_remove,
            netio_read_less_than, netio_read_remove,
            netio_write_less_than, netio_write_remove,
            last_stopped_at, host, crisis_bytes, metrics_port_start,
            environment, start_args
        )
        SELECT
            id, CpuCount, NodeCap, CpuLessThan, CpuRemove,
            MemLessThan, MemRemove, HDLessThan, HDRemove,
            DelayStart * ?, DelayUpgrade * ?, DelayRemove * ?,
            NodeStorage, RewardsAddress, DonateAddress,
            MaxLoadAverageAllowed, DesiredLoadAverage,
            PortStart, HDIOReadLessThan, HDIOReadRemove,
            HDIOWriteLessThan, HDIOWriteRemove,
            NetIOReadLessThan, NetIOReadRemove,
            NetIOWriteLessThan, NetIOWriteRemove,
            LastStoppedAt, Host, CrisisBytes, MetricsPortStart,
            Environment, StartArgs
        FROM machine
    """, (MINUTES_TO_SECONDS, MINUTES_TO_SECONDS, MINUTES_TO_SECONDS))

    # Drop old table and rename new one
    cursor.execute("DROP TABLE machine")
    cursor.execute("ALTER TABLE machine_new RENAME TO machine")

    logger.info("Machine table migrated successfully")
    logger.info(f"  - Delay timers converted from minutes to seconds (x{MINUTES_TO_SECONDS})")


def create_container_table(conn: sqlite3.Connection) -> None:
    """Create new Container table for Docker support"""
    logger.info("Creating Container table...")

    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS container (
            id INTEGER PRIMARY KEY,
            machine_id INTEGER DEFAULT 1,
            container_id TEXT UNIQUE,
            name TEXT,
            image TEXT,
            status TEXT,
            created_at INTEGER,
            FOREIGN KEY (machine_id) REFERENCES machine(id)
        )
    """)

    logger.info("Container table created successfully")


def migrate_node_table(conn: sqlite3.Connection) -> None:
    """Migrate Node table from nodename to node_name and add new fields"""
    logger.info("Migrating Node table...")

    cursor = conn.cursor()

    # Create new node table with snake_case and new fields
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS node_new (
            id INTEGER PRIMARY KEY,
            machine_id INTEGER DEFAULT 1,
            container_id INTEGER,
            manager_type TEXT DEFAULT 'systemd',
            node_name TEXT,
            service TEXT,
            user TEXT,
            binary TEXT,
            version TEXT,
            root_dir TEXT,
            port INTEGER,
            metrics_port INTEGER,
            network TEXT,
            wallet TEXT,
            peer_id TEXT,
            status TEXT,
            timestamp INTEGER,
            records INTEGER,
            uptime INTEGER,
            shunned INTEGER,
            age INTEGER,
            host TEXT,
            method TEXT,
            layout TEXT,
            environment TEXT,
            FOREIGN KEY (machine_id) REFERENCES machine(id),
            FOREIGN KEY (container_id) REFERENCES container(id)
        )
    """)

    # Create indices
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_node_wallet ON node_new(wallet)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_node_status ON node_new(status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_node_timestamp ON node_new(timestamp)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_node_records ON node_new(records)"
    )

    # Migrate data
    cursor.execute("""
        INSERT INTO node_new (
            id, node_name, service, user, binary, version, root_dir,
            port, metrics_port, network, wallet, peer_id, status,
            timestamp, records, uptime, shunned, age, host,
            method, layout, environment, machine_id, container_id, manager_type
        )
        SELECT
            id, nodename, service, user, binary, version, root_dir,
            port, metrics_port, network, wallet, peer_id, status,
            timestamp, records, uptime, shunned, age, host,
            method, layout, environment, 1, NULL, 'systemd'
        FROM node
    """)

    # Drop old table and rename new one
    cursor.execute("DROP TABLE node")
    cursor.execute("ALTER TABLE node_new RENAME TO node")

    logger.info("Node table migrated successfully")
    logger.info("  - nodename → node_name")
    logger.info("  - Added machine_id (default: 1)")
    logger.info("  - Added container_id (default: NULL)")
    logger.info("  - Added manager_type (default: 'systemd')")


def verify_migration(conn: sqlite3.Connection) -> bool:
    """Verify the migration was successful"""
    logger.info("Verifying migration...")

    cursor = conn.cursor()

    # Check machine table
    cursor.execute("SELECT COUNT(*) FROM machine")
    machine_count = cursor.fetchone()[0]
    logger.info(f"  Machine rows: {machine_count}")

    # Check node table
    cursor.execute("SELECT COUNT(*) FROM node")
    node_count = cursor.fetchone()[0]
    logger.info(f"  Node rows: {node_count}")

    # Check container table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='container'
    """)
    container_exists = cursor.fetchone() is not None
    logger.info(f"  Container table exists: {container_exists}")

    # Verify a few snake_case fields exist
    try:
        cursor.execute("SELECT cpu_count, node_cap, delay_start FROM machine LIMIT 1")
        row = cursor.fetchone()
        if row:
            logger.info(f"  Sample machine data: cpu_count={row[0]}, node_cap={row[1]}, delay_start={row[2]} seconds")

        cursor.execute("SELECT node_name, manager_type FROM node LIMIT 1")
        row = cursor.fetchone()
        if row:
            logger.info(f"  Sample node data: node_name={row[0]}, manager_type={row[1]}")

        logger.info("Migration verified successfully!")
        return True
    except sqlite3.OperationalError as e:
        logger.error(f"Verification failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Migrate WNM database from v0.0.9 to v1.0"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path.home() / ".local/share/wnm/colony.db",
        help="Path to colony.db (default: ~/.local/share/wnm/colony.db)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating a backup (not recommended)",
    )

    args = parser.parse_args()

    if not args.db_path.exists():
        logger.error(f"Database not found: {args.db_path}")
        sys.exit(1)

    logger.info(f"Migrating database: {args.db_path}")

    # Create backup
    if not args.no_backup:
        backup_path = backup_database(args.db_path)
        logger.info(f"Backup created: {backup_path}")
    else:
        logger.warning("Skipping backup (--no-backup flag set)")

    # Connect to database
    conn = sqlite3.connect(args.db_path)

    try:
        # Run migrations
        migrate_machine_table(conn)
        create_container_table(conn)
        migrate_node_table(conn)

        # Commit changes
        conn.commit()
        logger.info("Changes committed")

        # Verify
        if verify_migration(conn):
            logger.info("\n✅ Migration completed successfully!")
            logger.info("\nIMPORTANT: Delay timers are now in SECONDS (not minutes)")
            logger.info("  - If you had DelayStart=5 (5 minutes), it's now delay_start=300 (300 seconds)")
            logger.info("  - Update your config/expectations accordingly")
        else:
            logger.error("\n❌ Migration verification failed!")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        logger.error("Changes rolled back")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
