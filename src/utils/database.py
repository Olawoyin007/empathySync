"""
SQLite Database Layer for empathySync

Provides atomic transactions, schema versioning, and multi-device sync safety.
All data stays local. WAL mode enables crash-safe writes.

Usage:
    from utils.database import get_db, close_db, checkpoint_for_sync

    # Normal operations
    db = get_db()
    db.execute("INSERT INTO check_ins ...")
    db.commit()

    # Before switching devices
    checkpoint_for_sync()
    close_db()
"""

import sqlite3
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from config.settings import settings

logger = logging.getLogger(__name__)

# Current schema version - increment when schema changes
SCHEMA_VERSION = 3

# Thread-local storage for connections
_local = threading.local()

# Module-level connection for single-threaded Streamlit use
_connection: Optional[sqlite3.Connection] = None
_db_path: Optional[Path] = None


def get_db_path() -> Path:
    """Get the database file path."""
    return settings.DATA_DIR / "empathySync.db"


def get_db() -> sqlite3.Connection:
    """
    Get or create the database connection.

    Returns a connection configured with:
    - WAL mode for crash safety and concurrent reads
    - Foreign keys enabled
    - Row factory for dict-like access

    The connection is reused across calls (singleton pattern).
    """
    global _connection, _db_path

    db_path = get_db_path()

    # Return existing connection if valid
    if _connection is not None and _db_path == db_path:
        try:
            # Verify connection is still alive
            _connection.execute("SELECT 1")
            return _connection
        except sqlite3.Error:
            # Connection is dead, recreate
            _connection = None

    # Ensure directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Opening database: {db_path}")

    # Create connection
    conn = sqlite3.connect(
        db_path,
        timeout=30.0,  # Wait up to 30s for locks
        isolation_level=None,  # Autocommit mode, we'll manage transactions explicitly
        check_same_thread=False,  # Allow multi-threaded access (Streamlit)
    )

    # Enable WAL mode for crash safety
    conn.execute("PRAGMA journal_mode=WAL")

    # Full synchronous for durability (slower but safer for sync)
    conn.execute("PRAGMA synchronous=FULL")

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys=ON")

    # Row factory for dict-like access
    conn.row_factory = sqlite3.Row

    # Run startup recovery (checkpoint any leftover WAL)
    _startup_recovery(conn)

    # Initialize or migrate schema
    _ensure_schema(conn)

    _connection = conn
    _db_path = db_path

    return conn


def close_db():
    """
    Close the database connection cleanly.

    Should be called on app shutdown. Runs a checkpoint first
    to consolidate WAL for sync safety.
    """
    global _connection, _db_path

    if _connection is not None:
        try:
            # Checkpoint before close for sync safety
            checkpoint_for_sync()
            _connection.close()
            logger.info("Database closed cleanly")
        except sqlite3.Error as e:
            logger.error(f"Error closing database: {e}")
        finally:
            _connection = None
            _db_path = None


def checkpoint_for_sync() -> bool:
    """
    Run a full checkpoint to consolidate WAL into the main database.

    Call this before syncing or switching devices. The TRUNCATE mode
    merges all WAL content and truncates the WAL file to zero bytes,
    making the .db file self-contained.

    Returns True if checkpoint succeeded, False if busy/failed.
    Skipped in read-only mode (another device may be writing).
    """
    global _connection

    # Don't checkpoint in read-only mode - another device owns the lock
    try:
        from utils.write_gate import is_read_only

        if is_read_only():
            logger.info("Skipping checkpoint: read-only mode active")
            return False
    except ImportError:
        pass  # write_gate not available, proceed normally

    if _connection is None:
        logger.warning("Cannot checkpoint: no active connection")
        return False

    try:
        # TRUNCATE mode: checkpoint and truncate WAL to zero bytes
        # This requires exclusive lock, so close all cursors first
        result = _connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()

        # Result: (busy, log, checkpointed)
        # busy=1 means checkpoint was blocked
        if result and result[0] == 0:
            logger.info("WAL checkpoint completed successfully")
            return True
        else:
            logger.warning(f"WAL checkpoint returned: busy={result[0] if result else 'unknown'}")
            return False

    except sqlite3.Error as e:
        logger.error(f"Checkpoint failed: {e}")
        return False


def _startup_recovery(conn: sqlite3.Connection):
    """
    Run recovery on startup to handle leftover WAL/SHM from crashes.

    If the database was not cleanly closed (crash, force quit, sync mid-close),
    there may be uncommitted changes in the WAL. Running a checkpoint on startup
    settles the state.
    """
    db_path = get_db_path()
    wal_path = db_path.with_suffix(".db-wal")
    shm_path = db_path.with_suffix(".db-shm")

    # Check if WAL file exists and has content (indicates unclean close)
    if wal_path.exists() and wal_path.stat().st_size > 0:
        logger.info("Found non-empty WAL file, running recovery checkpoint")
        try:
            result = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
            logger.info(f"Recovery checkpoint: {result}")
        except sqlite3.Error as e:
            logger.warning(f"Recovery checkpoint failed (non-fatal): {e}")


def _ensure_schema(conn: sqlite3.Connection):
    """
    Ensure database schema is initialized and up to date.

    Creates tables if they don't exist, then runs any pending migrations.
    """
    # Check if schema_info table exists
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_info'"
    )
    schema_exists = cursor.fetchone() is not None

    if not schema_exists:
        logger.info("Initializing database schema")
        _create_schema(conn)
    else:
        _run_migrations(conn)


def _create_schema(conn: sqlite3.Connection):
    """Create the initial database schema (v1)."""

    conn.executescript(
        """
        -- Schema version tracking
        CREATE TABLE IF NOT EXISTS schema_info (
            version INTEGER PRIMARY KEY,
            migrated_at TEXT NOT NULL,
            description TEXT
        );

        -- Wellness check-ins (daily 1-5 scores)
        CREATE TABLE IF NOT EXISTS check_ins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            feeling_score INTEGER NOT NULL CHECK (feeling_score BETWEEN 1 AND 5),
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Usage sessions
        CREATE TABLE IF NOT EXISTS usage_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL DEFAULT (datetime('now')),
            ended_at TEXT,
            duration_minutes INTEGER,
            turn_count INTEGER DEFAULT 0,
            max_risk_weight REAL DEFAULT 0,
            domains_touched TEXT,  -- JSON array
            intent TEXT,  -- practical, processing, connection, unknown
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Policy events (transparency log)
        CREATE TABLE IF NOT EXISTS policy_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER REFERENCES usage_sessions(id),
            event_type TEXT NOT NULL,
            domain TEXT,
            action_taken TEXT NOT NULL,
            explanation TEXT,
            risk_weight REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Session intents (Phase 4 check-ins)
        CREATE TABLE IF NOT EXISTS session_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER REFERENCES usage_sessions(id),
            intent TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Independence records (competence graduation)
        CREATE TABLE IF NOT EXISTS independence_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_category TEXT NOT NULL,
            milestone TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Handoff events (human connection attempts)
        CREATE TABLE IF NOT EXISTS handoff_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            handoff_type TEXT NOT NULL,
            domain TEXT,
            person_name TEXT,
            completed INTEGER DEFAULT 0,  -- boolean
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Self-reports (user feedback)
        CREATE TABLE IF NOT EXISTS self_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_type TEXT NOT NULL,
            content TEXT,
            score INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Task patterns (for emotional weight tracking)
        CREATE TABLE IF NOT EXISTS task_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            count INTEGER DEFAULT 1,
            last_seen TEXT NOT NULL DEFAULT (datetime('now')),
            metadata TEXT,  -- JSON
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Trusted people (human network)
        CREATE TABLE IF NOT EXISTS trusted_people (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            relationship TEXT,
            contact TEXT,
            notes TEXT,
            domains TEXT,  -- JSON array
            added_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_contact TEXT
        );

        -- Reach-out history (cascade deletes when person is removed)
        CREATE TABLE IF NOT EXISTS reach_outs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER REFERENCES trusted_people(id) ON DELETE CASCADE,
            method TEXT,
            notes TEXT,
            outcome TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Create indexes for common queries
        CREATE INDEX IF NOT EXISTS idx_check_ins_created ON check_ins(created_at);
        CREATE INDEX IF NOT EXISTS idx_usage_sessions_started ON usage_sessions(started_at);
        CREATE INDEX IF NOT EXISTS idx_policy_events_created ON policy_events(created_at);
        CREATE INDEX IF NOT EXISTS idx_policy_events_session ON policy_events(session_id);

        -- Record initial schema version
        INSERT INTO schema_info (version, migrated_at, description)
        VALUES (1, datetime('now'), 'Initial schema');
    """
    )

    conn.commit()
    logger.info("Database schema v1 created")


def _run_migrations(conn: sqlite3.Connection):
    """Run any pending schema migrations."""

    # Get current version
    cursor = conn.execute("SELECT MAX(version) FROM schema_info")
    row = cursor.fetchone()
    current_version = row[0] if row and row[0] else 0

    if current_version >= SCHEMA_VERSION:
        return  # Already up to date

    logger.info(f"Migrating database from v{current_version} to v{SCHEMA_VERSION}")

    # Run migrations in order
    if current_version < 2:
        _migrate_v1_to_v2(conn)
    if current_version < 3:
        _migrate_v2_to_v3(conn)

    # Future migrations would go here


def _migrate_v1_to_v2(conn: sqlite3.Connection):
    """
    Add ON DELETE CASCADE to reach_outs foreign key.

    SQLite doesn't support ALTER TABLE for foreign key changes,
    so we recreate the table with the correct constraint.
    """
    logger.info("Running migration v1 -> v2: Adding cascade delete to reach_outs")

    conn.executescript(
        """
        -- Create new table with CASCADE constraint
        CREATE TABLE reach_outs_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER REFERENCES trusted_people(id) ON DELETE CASCADE,
            method TEXT,
            notes TEXT,
            outcome TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Copy existing data
        INSERT INTO reach_outs_new (id, person_id, method, notes, outcome, created_at)
        SELECT id, person_id, method, notes, outcome, created_at FROM reach_outs;

        -- Drop old table
        DROP TABLE reach_outs;

        -- Rename new table
        ALTER TABLE reach_outs_new RENAME TO reach_outs;

        -- Record migration
        INSERT INTO schema_info (version, migrated_at, description)
        VALUES (2, datetime('now'), 'Added ON DELETE CASCADE to reach_outs.person_id');
    """
    )

    # Verify no FK violations after rebuild
    violations = conn.execute("PRAGMA foreign_key_check(reach_outs)").fetchall()
    if violations:
        logger.error(f"FK violations after migration: {violations}")
        raise RuntimeError(f"Migration created {len(violations)} FK violations")

    conn.commit()
    logger.info("Migration v1 -> v2 completed")


def _migrate_v2_to_v3(conn: sqlite3.Connection):
    """
    Drop the dormant session_intents.user_input column.

    The write path for this column was removed in Phase 23.1 (raw user input
    must never be persisted); the column itself lingered as a standing capability
    to store message content. SQLite before 3.35 has no DROP COLUMN, so we
    recreate the table without it. The restraint-memory invariant
    (tests/test_restraint_memory.py) enforces that no such column returns.
    """
    logger.info("Running migration v2 -> v3: Dropping dormant session_intents.user_input")

    conn.executescript(
        """
        -- Recreate session_intents without the user_input column
        CREATE TABLE session_intents_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER REFERENCES usage_sessions(id),
            intent TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- Copy existing data (user_input is intentionally not carried over)
        INSERT INTO session_intents_new (id, session_id, intent, created_at)
        SELECT id, session_id, intent, created_at FROM session_intents;

        -- Drop old table
        DROP TABLE session_intents;

        -- Rename new table
        ALTER TABLE session_intents_new RENAME TO session_intents;

        -- Record migration
        INSERT INTO schema_info (version, migrated_at, description)
        VALUES (3, datetime('now'), 'Dropped dormant session_intents.user_input column');
    """
    )

    conn.commit()
    logger.info("Migration v2 -> v3 completed")


# ==================== CONVENIENCE FUNCTIONS ====================


@contextmanager
def transaction():
    """
    Context manager for explicit transactions.

    Usage:
        with transaction():
            db = get_db()
            db.execute("INSERT ...")
            db.execute("UPDATE ...")
        # Auto-commits on success, rolls back on exception
    """
    db = get_db()
    try:
        db.execute("BEGIN")
        yield db
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def execute_returning_id(sql: str, params: tuple = ()) -> int:
    """Execute an INSERT and return the new row's ID."""
    db = get_db()
    cursor = db.execute(sql, params)
    db.commit()
    return cursor.lastrowid


def fetch_one(sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    """Execute a query and return the first row."""
    db = get_db()
    cursor = db.execute(sql, params)
    return cursor.fetchone()


def fetch_all(sql: str, params: tuple = ()) -> List[sqlite3.Row]:
    """Execute a query and return all rows."""
    db = get_db()
    cursor = db.execute(sql, params)
    return cursor.fetchall()


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a sqlite3.Row to a regular dict."""
    if row is None:
        return {}
    return dict(zip(row.keys(), row))


# ==================== MIGRATION FROM JSON ====================


def migrate_from_json(wellness_json_path: Path, network_json_path: Path) -> bool:
    """
    Migrate existing JSON data to SQLite.

    This is a one-time migration. After successful migration,
    the JSON files should be archived (not deleted, for safety).

    Returns True if migration succeeded.
    """
    import json

    db = get_db()

    try:
        # Migrate wellness data
        if wellness_json_path.exists():
            logger.info(f"Migrating wellness data from {wellness_json_path}")
            with open(wellness_json_path) as f:
                wellness = json.load(f)

            with transaction():
                # Check-ins
                for checkin in wellness.get("check_ins", []):
                    db.execute(
                        "INSERT INTO check_ins (feeling_score, notes, created_at) VALUES (?, ?, ?)",
                        (
                            checkin.get("score", checkin.get("feeling_score", 3)),
                            checkin.get("notes", ""),
                            checkin.get(
                                "timestamp", checkin.get("created_at", datetime.now().isoformat())
                            ),
                        ),
                    )

                # Usage sessions
                for session in wellness.get("usage_sessions", []):
                    db.execute(
                        """INSERT INTO usage_sessions
                           (started_at, ended_at, duration_minutes, turn_count, max_risk_weight, domains_touched)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            session.get("started_at", session.get("start_time")),
                            session.get("ended_at", session.get("end_time")),
                            session.get("duration_minutes", session.get("duration")),
                            session.get("turn_count", session.get("turns", 0)),
                            session.get("max_risk_weight", session.get("max_risk", 0)),
                            json.dumps(session.get("domains_touched", session.get("domains", []))),
                        ),
                    )

                # Policy events
                for event in wellness.get("policy_events", []):
                    db.execute(
                        """INSERT INTO policy_events
                           (event_type, domain, action_taken, explanation, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            event.get("type", event.get("event_type", "unknown")),
                            event.get("domain"),
                            event.get("action", event.get("action_taken", "")),
                            event.get("explanation", event.get("reason", "")),
                            event.get(
                                "timestamp", event.get("created_at", datetime.now().isoformat())
                            ),
                        ),
                    )

                # Session intents
                for intent in wellness.get("session_intents", []):
                    db.execute(
                        "INSERT INTO session_intents (intent, created_at) VALUES (?, ?)",
                        (
                            intent.get("intent", "unknown"),
                            intent.get(
                                "timestamp", intent.get("created_at", datetime.now().isoformat())
                            ),
                        ),
                    )

                # Independence records
                for record in wellness.get("independence_records", []):
                    db.execute(
                        "INSERT INTO independence_records (task_category, milestone, notes, created_at) VALUES (?, ?, ?, ?)",
                        (
                            record.get("task_category", record.get("category", "")),
                            record.get("milestone", ""),
                            record.get("notes", ""),
                            record.get(
                                "timestamp", record.get("created_at", datetime.now().isoformat())
                            ),
                        ),
                    )

                # Handoff events
                for handoff in wellness.get("handoff_events", []):
                    db.execute(
                        """INSERT INTO handoff_events
                           (handoff_type, domain, person_name, completed, notes, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            handoff.get("type", handoff.get("handoff_type", "")),
                            handoff.get("domain"),
                            handoff.get("person_name", handoff.get("person", "")),
                            1 if handoff.get("completed") else 0,
                            handoff.get("notes", ""),
                            handoff.get(
                                "timestamp", handoff.get("created_at", datetime.now().isoformat())
                            ),
                        ),
                    )

                # Self-reports
                for report in wellness.get("self_reports", []):
                    db.execute(
                        "INSERT INTO self_reports (report_type, content, score, created_at) VALUES (?, ?, ?, ?)",
                        (
                            report.get("type", report.get("report_type", "")),
                            report.get("content", ""),
                            report.get("score"),
                            report.get(
                                "timestamp", report.get("created_at", datetime.now().isoformat())
                            ),
                        ),
                    )

            logger.info(
                f"Migrated wellness data: {len(wellness.get('check_ins', []))} check-ins, "
                f"{len(wellness.get('usage_sessions', []))} sessions"
            )

        # Migrate trusted network
        if network_json_path.exists():
            logger.info(f"Migrating trusted network from {network_json_path}")
            with open(network_json_path) as f:
                network = json.load(f)

            with transaction():
                # Trusted people
                id_map = {}  # old_id -> new_id for reach_outs FK
                for person in network.get("people", []):
                    cursor = db.execute(
                        """INSERT INTO trusted_people
                           (name, relationship, contact, notes, domains, added_at, last_contact)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            person.get("name", ""),
                            person.get("relationship", ""),
                            person.get("contact", ""),
                            person.get("notes", ""),
                            json.dumps(person.get("domains", [])),
                            person.get("added_at", datetime.now().isoformat()),
                            person.get("last_contact"),
                        ),
                    )
                    if person.get("id"):
                        id_map[person["id"]] = cursor.lastrowid

                # Reach-outs
                for reach_out in network.get("reach_outs", []):
                    # Try to find person by name if no id mapping
                    person_id = None
                    if reach_out.get("person_id") and reach_out["person_id"] in id_map:
                        person_id = id_map[reach_out["person_id"]]
                    elif reach_out.get("person_name"):
                        row = db.execute(
                            "SELECT id FROM trusted_people WHERE name = ?",
                            (reach_out["person_name"],),
                        ).fetchone()
                        if row:
                            person_id = row[0]

                    db.execute(
                        "INSERT INTO reach_outs (person_id, method, notes, created_at) VALUES (?, ?, ?, ?)",
                        (
                            person_id,
                            reach_out.get("method", ""),
                            reach_out.get("notes", ""),
                            reach_out.get(
                                "timestamp", reach_out.get("created_at", datetime.now().isoformat())
                            ),
                        ),
                    )

            logger.info(
                f"Migrated trusted network: {len(network.get('people', []))} people, "
                f"{len(network.get('reach_outs', []))} reach-outs"
            )

        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
