#!/usr/bin/env python3
"""
Migration script to add connected_peers column to the node table.

This script adds the connected_peers field to existing databases.
It can be run safely multiple times - it will skip if the column already exists.
"""

import sys
import os
import sqlite3
from pathlib import Path

# Add src to path so we can import wnm modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def migrate_database(db_path):
    """
    Add connected_peers column to the node table if it doesn't exist.

    Args:
        db_path: Path to the SQLite database file
    """
    print(f"Migrating database: {db_path}")

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if connected_peers column already exists
        cursor.execute("PRAGMA table_info(node)")
        columns = [row[1] for row in cursor.fetchall()]

        if "connected_peers" in columns:
            print("  ✓ connected_peers column already exists, skipping migration")
            return True

        # Add the column with default value of 0
        print("  + Adding connected_peers column...")
        cursor.execute("ALTER TABLE node ADD COLUMN connected_peers INTEGER DEFAULT 0")

        # Update existing rows to have 0 for connected_peers
        cursor.execute("UPDATE node SET connected_peers = 0 WHERE connected_peers IS NULL")

        conn.commit()
        print("  ✓ Migration completed successfully")
        return True

    except sqlite3.Error as e:
        print(f"  ✗ Error during migration: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


def find_database():
    """
    Find the colony.db database file.

    Looks in:
    1. Current directory
    2. macOS default: ~/Library/Application Support/autonomi/colony.db
    3. Linux root: /var/antctl/colony.db
    4. Linux user: ~/.local/share/autonomi/colony.db
    """
    # Check current directory first
    if os.path.exists("colony.db"):
        return "colony.db"

    # Check platform-specific locations
    if sys.platform == "darwin":
        # macOS
        macos_path = Path.home() / "Library/Application Support/autonomi/colony.db"
        if macos_path.exists():
            return str(macos_path)
    else:
        # Linux
        root_path = Path("/var/antctl/colony.db")
        user_path = Path.home() / ".local/share/autonomi/colony.db"

        if root_path.exists():
            return str(root_path)
        elif user_path.exists():
            return str(user_path)

    return None


def main():
    """Main migration entry point."""
    print("Colony Database Migration: Add connected_peers field")
    print("=" * 60)

    # Check for database path argument
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = find_database()

    if not db_path:
        print("\n✗ Could not find colony.db")
        print("\nPlease specify the database path:")
        print("  python3 migrate_add_connected_peers.py /path/to/colony.db")
        return 1

    if not os.path.exists(db_path):
        print(f"\n✗ Database file not found: {db_path}")
        return 1

    # Create backup
    backup_path = f"{db_path}.backup"
    print(f"\nCreating backup: {backup_path}")
    import shutil
    shutil.copy2(db_path, backup_path)
    print("  ✓ Backup created")

    # Run migration
    print()
    success = migrate_database(db_path)

    if success:
        print("\n✓ Migration completed successfully")
        print(f"  Backup saved at: {backup_path}")
        return 0
    else:
        print("\n✗ Migration failed")
        print(f"  Database backup available at: {backup_path}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
