# Data Persistence & Multi-Device Sync

This document covers empathySync's local data storage strategy, including atomic writes, schema versioning, SQLite backend, and multi-device sync with write protection.

## Design Constraints

| Constraint | Rationale |
|------------|-----------|
| **Local-first** | No external API calls; user data never leaves their devices |
| **Single user** | No multi-tenant isolation needed |
| **Multiple devices** | User may run on laptop + desktop, but only one device at a time |
| **Sync via file sync tools** | Dropbox, Syncthing, iCloud -not custom sync protocol |
| **Defense-in-depth** | Multiple layers prevent accidental data corruption |

## Storage Backends

empathySync supports two storage backends:

| Backend | Enable | Best For |
|---------|--------|----------|
| **JSON** (default) | `USE_SQLITE=false` | Simple setups, human-readable data |
| **SQLite** | `USE_SQLITE=true` | Multi-device sync, better transactions |

## JSON Backend: Atomic Writes

Both data files use atomic writes to prevent corruption:

```
data/
├── wellness_data.json      # Session tracking, check-ins, policy events
└── trusted_network.json    # Trusted contacts, reach-out history
```

### Write Pattern

```python
# 1. Write to temp file in same directory
fd, temp_path = tempfile.mkstemp(dir=data_dir, prefix=".wellness_data_", suffix=".tmp")

# 2. Write JSON and force to disk
with os.fdopen(fd, 'w') as f:
    json.dump(data, f, indent=2)
    f.flush()
    os.fsync(f.fileno())

# 3. Atomic rename (POSIX guarantees atomicity on same filesystem)
os.replace(temp_path, final_path)
```

**Why this works:** `os.replace()` is atomic on POSIX systems when source and target are on the same filesystem. Either the old file exists or the new one does -never a partial write.

### Schema Versioning

All data files now include a `schema_version` field:

```json
{
  "schema_version": 1,
  "check_ins": [...],
  "usage_sessions": [...],
  ...
}
```

**Migration flow:**
1. On load, check `schema_version` (defaults to 0 if missing)
2. If version < current, run migration functions sequentially
3. Save migrated data with updated version

**Adding future migrations:**
```python
def _migrate_schema(self, data: Dict) -> Dict:
    current_version = data.get("schema_version", 0)

    if current_version < 1:
        # v0 -> v1: Add schema_version, ensure all fields exist
        data["schema_version"] = 1
        ...

    if current_version < 2:
        # v1 -> v2: Example future migration
        data = self._migrate_v1_to_v2(data)

    return data
```

### Corruption Recovery

If JSON parsing fails:
1. Corrupted file backed up as `wellness_data.corrupted.{timestamp}.json`
2. Fresh defaults returned (data loss, but no crash)
3. Error logged for debugging

```
Corrupted wellness data file: Expecting property name...
Corrupted file backed up to: data/wellness_data.corrupted.20260127_234827.json
```

## SQLite Backend (Implemented)

SQLite provides stronger guarantees for the multi-device use case.

### Why SQLite?

| Feature | JSON | SQLite |
|---------|------|--------|
| Atomic commits | Manual (temp+rename) | Built-in transactions |
| Schema migration | Custom code | Well-established patterns |
| Partial updates | Read-modify-write entire file | Update single rows |
| Query capability | Load entire file | SQL queries |
| Concurrent reads | File lock contention | WAL mode allows concurrent reads |

### Enable SQLite

```bash
# .env
USE_SQLITE=true
```

### WAL Mode Configuration

SQLite's Write-Ahead Logging (WAL) mode is enabled automatically:

```
data/empathySync.db      # Main database file
data/empathySync.db-wal  # Write-ahead log (uncommitted changes)
data/empathySync.db-shm  # Shared memory (coordination)
```

**Durability settings (automatic):**
```sql
PRAGMA journal_mode = WAL;       -- Crash safety
PRAGMA synchronous = FULL;       -- Durability over speed
PRAGMA foreign_keys = ON;        -- Enforced per-connection
```

**Checkpoint behavior:**
- On clean app close: `wal_checkpoint(TRUNCATE)` consolidates WAL into main DB
- In read-only mode: Checkpoint is skipped (another device may be writing)

### Schema (v2)

```sql
-- Schema version tracking
CREATE TABLE schema_info (
    version INTEGER PRIMARY KEY,
    migrated_at TEXT NOT NULL,
    description TEXT
);

-- Wellness check-ins
CREATE TABLE check_ins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feeling_score INTEGER NOT NULL CHECK (feeling_score BETWEEN 1 AND 5),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Usage sessions
CREATE TABLE usage_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    duration_minutes INTEGER,
    turn_count INTEGER DEFAULT 0,
    max_risk_weight REAL DEFAULT 0,
    domains_touched TEXT,  -- JSON array
    intent TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Policy events (transparency log)
CREATE TABLE policy_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    domain TEXT,
    action_taken TEXT NOT NULL,
    risk_weight REAL DEFAULT 0,
    explanation TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Trusted network
CREATE TABLE trusted_people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    relationship TEXT,
    contact TEXT,
    notes TEXT,
    domains TEXT,  -- JSON array
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_contact TEXT
);

-- Reach-out history (CASCADE on person delete - v2)
CREATE TABLE reach_outs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER REFERENCES trusted_people(id) ON DELETE CASCADE,
    method TEXT,
    notes TEXT,
    outcome TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### Schema Migrations

| Version | Description |
|---------|-------------|
| v1 | Initial schema |
| v2 | Added `ON DELETE CASCADE` to reach_outs foreign key |
| v3 | Dropped the dormant `session_intents.user_input` column (raw message text must never be persistable; enforced by the restraint-memory invariant) |

Migrations run automatically on startup via `_run_migrations()` in `database.py`. After migration, `PRAGMA foreign_key_check` verifies no FK violations.

## Lock File Mechanism (Implemented)

For single-active-device sync, a lock file prevents concurrent access across devices.

### Enable Device Lock

```bash
# .env
ENABLE_DEVICE_LOCK=true
LOCK_STALE_TIMEOUT=300  # seconds until lock is stale (default: 300)
```

### Design: Heartbeat-Based Lock

```
data/
├── empathySync.db
├── .empathySync.lock    # Lock file with heartbeat
└── .device_id           # Persistent device identifier
```

**Lock file contents:**
```json
{
  "device_id": "my-macbook-a1b2c3d4",
  "hostname": "my-macbook",
  "pid": 12345,
  "started_at": "2026-01-27T10:30:00Z",
  "heartbeat": "2026-01-27T10:35:00Z"
}
```

**Why heartbeat, not PID?**
- PIDs can be reused after reboot
- Stale locks from crashed apps need detection
- Heartbeat timeout (configurable via `LOCK_STALE_TIMEOUT`) indicates crash or forgotten session
- Device ID is persistent across sessions (stored in `.device_id` file)

**Lock acquisition flow:**
```
1. Check if .lock exists
2. If exists:
   a. Read heartbeat timestamp
   b. If heartbeat > LOCK_STALE_TIMEOUT old → stale lock, acquire
   c. If our own device → refresh lock (handles crash recovery)
   d. If another device, fresh lock → warn user, enter read-only mode
3. If not exists → create lock
4. Start heartbeat thread (update every 60 seconds)
5. On clean shutdown → delete lock
```

**UI behavior when lock detected:**
```
⚠️ Read-only mode: empathySync is open on my-macbook (since 10:30 AM).
   Writes are blocked to prevent sync conflicts. Close it there first.

   [Take Over]  [Dismiss]
```

**Sidebar indicator:**
```
🔴 Writes blocked - another device has the lock
```

## Write Gate (Defense-in-Depth)

When another device holds the lock, all write operations are blocked at multiple levels:

### Protection Layers

| Layer | Implementation | Purpose |
|-------|---------------|---------|
| **1. UI** | Chat input disabled, buttons hidden | User can't initiate writes |
| **2. Write Gate** | `set_read_only(True)` in `write_gate.py` | Centralized flag |
| **3. Storage** | `_ensure_write_allowed()` in every write method | Enforcement |
| **4. Checkpoint** | Skipped when `is_read_only()` | Prevents DB mutation |

### Write Gate API

```python
from utils.write_gate import set_read_only, is_read_only, check_write_permission, WriteBlockedError

# Called by app.py when lock status changes
set_read_only(True)   # Another device has lock
set_read_only(False)  # We acquired lock

# Called by storage backends before any write
check_write_permission()  # Raises WriteBlockedError if blocked

# Check current state
if is_read_only():
    print("Writes are blocked")
```

### Protected Operations

All 31 write methods in both JSON and SQLite backends call `_ensure_write_allowed()`:
- `add_check_in()`, `add_session()`, `add_policy_event()`
- `add_trusted_person()`, `update_trusted_person()`, `remove_trusted_person()`
- `add_reach_out()`, `add_handoff_event()`, `add_self_report()`
- `record_task_pattern()`, `update_task_pattern()`
- `clear_all_data()`
- And more...

### Fail-Open vs Fail-Closed

The system uses **fail-open** design: if the lock file system breaks (corrupted lock, disk error), writes are allowed. Rationale:
- Single-user local app; corrupted lock shouldn't brick the app
- User can always manually delete `.empathySync.lock`
- Preference for usability over absolute data consistency

## Multi-Device Sync Strategy

### Supported Sync Tools

| Tool | Notes |
|------|-------|
| **Syncthing** | Recommended. Peer-to-peer, no cloud. Handles conflicts well. |
| **Dropbox** | Works, but may create conflict copies on simultaneous edits |
| **iCloud Drive** | Works on Apple devices |
| **OneDrive** | Works, similar to Dropbox |
| **Git** | Not recommended (binary DB diffs poorly) |

### Operating Rules

1. **Close app before switching devices**
   - Ensures checkpoint completes
   - Lock file removed
   - Sync tool can safely transfer files

2. **Wait for sync to complete**
   - Syncthing: green icon, no pending changes
   - Dropbox: checkmark on files

3. **If conflict copies appear**
   - Indicates simultaneous use (shouldn't happen with lock)
   - Manual merge may be needed
   - SQLite can't auto-merge like CRDTs

### Recommended Sync Folder Structure

```
~/Sync/empathySync/          # Synced folder
├── data/
│   ├── empathySync.db       # Database
│   ├── empathySync.db-wal   # (may not exist after clean close)
│   ├── empathySync.db-shm   # (may not exist after clean close)
│   └── .empathySync.lock    # Lock file
└── logs/                    # Optional: sync logs too
```

Configure empathySync to use this data directory:
```bash
# .env
DATA_DIR=/Users/me/Sync/empathySync/data
```

## Migration Path: JSON → SQLite

When ready to migrate:

1. **Backup existing JSON files**
2. **Run migration script** (one-time)
   - Read all JSON data
   - Insert into SQLite tables
   - Verify row counts match
3. **Update code** to use SQLite
4. **Archive JSON files** (keep for rollback)

```python
def migrate_json_to_sqlite():
    # Load existing JSON
    with open("data/wellness_data.json") as f:
        wellness = json.load(f)
    with open("data/trusted_network.json") as f:
        network = json.load(f)

    # Insert into SQLite
    conn = sqlite3.connect("data/empathySync.db")

    for checkin in wellness.get("check_ins", []):
        conn.execute(
            "INSERT INTO check_ins (feeling_score, notes, created_at) VALUES (?, ?, ?)",
            (checkin["score"], checkin.get("notes"), checkin["timestamp"])
        )

    # ... similar for other tables

    conn.commit()

    # Archive old files
    shutil.move("data/wellness_data.json", "data/archive/wellness_data.json.bak")
```

## Future: Event Log Architecture (If Needed)

If requirements change to support true simultaneous multi-device use, the architecture would shift to:

```
Append-only event log → Sync events → Replay/merge on each device
```

This is a CRDT-like pattern where:
- Each event has UUID, timestamp, device_id
- Events are never modified, only appended
- State is rebuilt by replaying events
- Merge conflicts are resolved by deterministic rules

**Not needed for current requirements** (single-active-device), but documented here for future reference.

---

## Summary

| Phase | Status | Description |
|-------|--------|-------------|
| Atomic JSON writes | ✅ Done | Prevents corruption from interrupted writes |
| Schema versioning | ✅ Done | Enables safe data migrations (JSON: v1, SQLite: v2) |
| SQLite backend | ✅ Done | WAL mode, transactions, foreign keys, cascade deletes |
| Lock file mechanism | ✅ Done | Heartbeat-based, configurable timeout, stale detection |
| Write gate | ✅ Done | Defense-in-depth protection for read-only mode |
| Sync folder docs | ✅ Done | User guide: [sync-setup.md](sync-setup.md) |

## Configuration Reference

```bash
# .env

# Storage backend (default: false = JSON)
USE_SQLITE=true

# Multi-device lock (default: false)
ENABLE_DEVICE_LOCK=true

# Lock stale timeout in seconds (default: 300)
LOCK_STALE_TIMEOUT=300
```

---

See also:
- [Architecture Overview](architecture.md)
- [CLAUDE.md](../CLAUDE.md) for code-level details
