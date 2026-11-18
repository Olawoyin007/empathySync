"""
Restraint-memory invariant over the whole StorageBackend write surface (#236).

tests/test_restraint_memory.py exercises a hand-written list of calls and then
checks the allowlist. That catches a new field on a path the list happens to
cover; it cannot catch one on a path the list forgot, because the assertion only
ever sees what was written.

This file drives the write surface instead of a list of calls. Write methods are
discovered by introspection - a public method whose body calls
`_ensure_write_allowed()` is a write path, which is the same gate the write-gate
control uses - and their arguments are generated from their type hints with
hypothesis. A write method added later is picked up with no edit here, and an
argument type nobody wrote a strategy for fails loudly rather than being skipped.

The allowlist check is duplicated from test_restraint_memory.py rather than
imported, deliberately: that file is a blocking CI gate and this one must not be
able to weaken it by refactoring it.
"""

import inspect
import json
import sqlite3
import sys
import tempfile
import typing
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tests.test_restraint_memory import ALLOWLIST_PATH, STRUCTURE_MAP  # noqa: E402

# clear_all_data would delete the evidence this test is about to inspect.
NOT_GENERATED = {"clear_all_data"}

# These three merge a caller-supplied dict straight into a persisted record.
# SQLite rejects an unallowlisted key through its column whitelist; the JSON
# backend - the default - does not, so generated keys land in the file. They are
# driven by their own test below rather than silently left out of this one.
UNFILTERED_UPDATE_PATHS = {
    "update_task_pattern",
    "update_trusted_person",
    "update_handoff_event",
}

# Fields JSONBackend writes that restraint_memory.allowed_fields does not list.
#
# With USE_SQLITE false - the default - WellnessTracker and TrustedNetwork write
# the JSON files themselves and only delegate to the backend when SQLite is on
# (18 methods gate on `settings.USE_SQLITE`). JSONBackend's record builders are
# therefore unreached in a default install, where it serves reads and
# prune_old_data only. The allowlist was written against the shapes the app
# actually writes, and the backend's shapes have drifted from them.
#
# None of these is conversation content or persona data, so the invariant's
# substance holds. They are recorded rather than allowlisted because adding them
# to restraint_memory would assert they were reviewed as things worth persisting,
# and the real question is why there are two JSON writers at all.
#
# A field not listed here still fails. test_recorded_drift_is_still_real below
# fails if an entry stops being written, so the list cannot quietly rot.
KNOWN_JSON_DRIFT = {
    ("wellness_data.json", "check_ins"): {"id"},
    ("wellness_data.json", "usage_sessions"): {"id", "intent"},
    ("wellness_data.json", "policy_events"): {"event_type", "explanation", "id"},
    ("wellness_data.json", "session_intents"): {"id"},
    ("wellness_data.json", "independence_records"): {"id", "milestone", "task_category"},
    ("wellness_data.json", "handoff_events"): {
        "completed",
        "handoff_type",
        "id",
        "notes",
        "person_name",
    },
    ("wellness_data.json", "task_patterns"): {"metadata"},
    ("trusted_network.json", "reach_outs"): {"id", "outcome", "person_id"},
}


@pytest.fixture(scope="module")
def restraint_config():
    return yaml.safe_load(open(ALLOWLIST_PATH))["restraint_memory"]


def _write_methods(backend):
    """Public methods that pass through the write gate, by their own source."""
    found = {}
    for name in dir(backend):
        if name.startswith("_"):
            continue
        attr = getattr(backend, name)
        if not callable(attr):
            continue
        try:
            source = inspect.getsource(attr)
        except (TypeError, OSError):
            continue
        if "_ensure_write_allowed()" in source:
            found[name] = attr
    return found


def _strategy_for(annotation):
    """A strategy per annotated argument type. Unknown types are a failure."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return st.one_of(st.none(), *[_strategy_for(a) for a in args])
    if origin in (list, typing.List):
        (inner,) = typing.get_args(annotation) or (str,)
        return st.lists(_strategy_for(inner), max_size=3)
    if origin in (dict, typing.Dict):
        return st.dictionaries(st.text(max_size=12), st.text(max_size=12), max_size=3)
    if annotation in (typing.Dict, dict):
        return st.dictionaries(st.text(max_size=12), st.text(max_size=12), max_size=3)
    if annotation in (typing.List, list):
        return st.lists(st.text(max_size=12), max_size=3)
    if annotation is bool:
        return st.booleans()
    if annotation is int:
        return st.integers(min_value=0, max_value=10)
    if annotation is float:
        return st.floats(min_value=0, max_value=10, allow_nan=False, allow_infinity=False)
    if annotation is str:
        return st.text(max_size=20)
    if annotation is date:
        return st.dates()
    raise AssertionError(
        f"no strategy for annotation {annotation!r} - add one rather than "
        "letting this argument go ungenerated"
    )


def _draw_kwargs(data, method, overrides):
    """Generated values for every annotated parameter, minus any override."""
    hints = typing.get_type_hints(method)
    kwargs = {}
    for name in inspect.signature(method).parameters:
        if name in ("self", "return"):
            continue
        if name in overrides:
            kwargs[name] = overrides[name]
            continue
        annotation = hints.get(name)
        if annotation is None:
            continue
        kwargs[name] = data.draw(_strategy_for(annotation), label=f"{method.__name__}.{name}")
    return kwargs


def _fresh_backend(tmp_path, use_sqlite):
    """A backend rooted at tmp_path, with the singleton and db handle reset."""
    import utils.database as db_module
    from utils.storage_backend import get_storage_backend, reset_storage_backend

    db_module._connection = None
    db_module._db_path = None
    reset_storage_backend()

    patches = [
        patch(f"{module}.settings")
        for module in ("utils.storage_backend", "utils.database", "config.settings")
    ]
    mocks = [p.start() for p in patches]
    for mock in mocks:
        mock.DATA_DIR = tmp_path
        mock.USE_SQLITE = use_sqlite
        mock.ENABLE_DEVICE_LOCK = False
        mock.DATA_RETENTION_DAYS = 90
    return get_storage_backend(), patches


def _teardown_backend(patches, use_sqlite):
    import utils.database as db_module
    from utils.storage_backend import reset_storage_backend

    if use_sqlite:
        db_module.close_db()
        db_module._connection = None
        db_module._db_path = None
    reset_storage_backend()
    for p in patches:
        p.stop()


def _seed(backend):
    """
    One real record per container, so the update_* paths have something to hit.

    Without this they return early on a missing id and the generated updates are
    never applied to anything.
    """
    backend.record_task_pattern("email_drafting")
    person = backend.add_trusted_person("Sam", relationship="friend")
    handoff = backend.add_handoff_event("initiated", domain="relationships")
    return {
        "pattern_type": "email_drafting",
        "person_id": person["id"],
        "event_id": handoff["id"],
    }


def _assert_json_allowlisted(tmp_path, allowed):
    for filename, structure in STRUCTURE_MAP.items():
        path = tmp_path / filename
        if not path.exists():
            continue
        payload = json.load(open(path))

        unexpected = set(payload.keys()) - set(allowed[structure["_root"]])
        assert not unexpected, f"{filename} top level persists {sorted(unexpected)}"

        for key, entry_name in structure.items():
            if key == "_root":
                continue
            drift = KNOWN_JSON_DRIFT.get((filename, key), set())
            for record in payload.get(key, []):
                unexpected = set(record.keys()) - set(allowed[entry_name]) - drift
                assert not unexpected, f"{filename}:{key} persists {sorted(unexpected)}"

        drift = KNOWN_JSON_DRIFT.get((filename, "task_patterns"), set())
        for category, stats in payload.get("task_patterns", {}).items():
            unexpected = set(stats.keys()) - set(allowed["task_patterns"]) - drift
            assert not unexpected, f"task_patterns[{category}] persists {sorted(unexpected)}"
            for use in stats.get("uses", []):
                unexpected = set(use.keys()) - set(allowed["task_pattern_uses"])
                assert not unexpected, f"task_patterns uses persist {sorted(unexpected)}"


def _assert_sqlite_allowlisted(tmp_path, allowed_columns):
    db_files = list(tmp_path.glob("*.db"))
    assert db_files, "SQLite backend did not create a database file"
    conn = sqlite3.connect(db_files[0])
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            assert table in allowed_columns, f"table '{table}' is not allowlisted"
            for row in conn.execute(f"PRAGMA table_info({table})"):
                assert (
                    row[1] in allowed_columns[table]
                ), f"table '{table}' column '{row[1]}' is not allowlisted"
    finally:
        conn.close()


def test_the_write_surface_was_actually_discovered(tmp_path):
    """A discovery bug would make every property below vacuously true."""
    backend, patches = _fresh_backend(tmp_path, use_sqlite=False)
    try:
        methods = _write_methods(backend)
    finally:
        _teardown_backend(patches, use_sqlite=False)

    assert len(methods) >= 16, f"only found {len(methods)} write methods: {sorted(methods)}"
    for excluded in (NOT_GENERATED, UNFILTERED_UPDATE_PATHS):
        assert excluded <= set(methods), (
            f"{sorted(excluded - set(methods))} is named in an exclusion set but is no "
            "longer a write method - drop it from that set rather than leaving a stale name"
        )
    for name in ("add_check_in", "update_task_pattern", "update_trusted_person"):
        assert name in methods, f"{name} should have been discovered as a write path"


@pytest.mark.parametrize("use_sqlite", [False, True], ids=["json", "sqlite"])
@given(data=st.data())
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_generated_writes_never_persist_an_unallowlisted_field(restraint_config, use_sqlite, data):
    """
    Drive every discovered write method with generated arguments, then re-check
    the allowlist. Any single call may legitimately reject its input; what must
    never happen is a field outside the allowlist reaching the file or the table.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        backend, patches = _fresh_backend(tmp_path, use_sqlite)
        try:
            overrides = _seed(backend)
            for name, method in sorted(_write_methods(backend).items()):
                if name in NOT_GENERATED or name in UNFILTERED_UPDATE_PATHS:
                    continue
                kwargs = _draw_kwargs(data, method, overrides)
                try:
                    method(**kwargs)
                except (ValueError, TypeError, KeyError, sqlite3.Error):
                    # Rejecting generated junk is fine. Persisting it is not.
                    pass

            if use_sqlite:
                _assert_sqlite_allowlisted(tmp_path, restraint_config["allowed_columns"])
            else:
                _assert_json_allowlisted(tmp_path, restraint_config["allowed_fields"])
        finally:
            _teardown_backend(patches, use_sqlite)


@pytest.mark.parametrize("use_sqlite", [False, True], ids=["json", "sqlite"])
@given(key=st.sampled_from(["conversation_text", "persona_summary", "transcript", "zzz_unknown"]))
@settings(max_examples=4, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_update_paths_reject_an_unallowlisted_key(use_sqlite, key):
    """
    The write boundary itself should refuse a field outside the allowlist.

    SQLite does, through the column whitelist that backs the no-SQL-injection
    control. The JSON backend - the default - calls `.update(updates)` and
    persists whatever it is handed, so the invariant there rests on every caller
    choosing allowlisted keys rather than on the boundary enforcing them.

    Nothing in `src/` currently passes arbitrary keys down these three paths, so
    no field is being persisted wrongly today. The xfail below records that the
    guarantee is held by convention on the default backend, and will turn into an
    XPASS the moment the JSON path filters its keys.
    """
    if not use_sqlite:
        pytest.xfail("JSON backend merges caller dicts unfiltered (found by #236)")

    with tempfile.TemporaryDirectory() as tmp:
        backend, patches = _fresh_backend(Path(tmp), use_sqlite)
        try:
            overrides = _seed(backend)
            for name in sorted(UNFILTERED_UPDATE_PATHS):
                method = getattr(backend, name)
                arg = {
                    "update_task_pattern": {"pattern_type": overrides["pattern_type"]},
                    "update_trusted_person": {"person_id": overrides["person_id"]},
                    "update_handoff_event": {"event_id": overrides["event_id"]},
                }[name]
                with pytest.raises((ValueError, sqlite3.Error)):
                    method(**arg, updates={key: "something the user said"})
        finally:
            _teardown_backend(patches, use_sqlite)


def _sane_value(annotation):
    """A plausible argument per type, for the deterministic drift sweep."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        inner = [a for a in typing.get_args(annotation) if a is not type(None)]
        return _sane_value(inner[0])
    if origin in (list, typing.List) or annotation in (typing.List, list):
        return ["logistics"]
    if origin in (dict, typing.Dict) or annotation in (typing.Dict, dict):
        return {"k": "v"}
    return {bool: True, int: 3, float: 1.0, str: "x", date: date.today()}.get(annotation, "x")


def test_recorded_drift_is_still_real(restraint_config):
    """
    Every field in KNOWN_JSON_DRIFT must still be written by JSONBackend.

    Without this, a shape that gets fixed leaves a permanent hole in the
    allowlist check above - the recorded gap would go on excusing a field that
    could later come back for a different reason.
    """
    allowed = restraint_config["allowed_fields"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        backend, patches = _fresh_backend(tmp_path, use_sqlite=False)
        try:
            for name, method in sorted(_write_methods(backend).items()):
                if name in NOT_GENERATED or name in UNFILTERED_UPDATE_PATHS:
                    continue
                hints = typing.get_type_hints(method)
                kwargs = {
                    p: _sane_value(hints[p])
                    for p in inspect.signature(method).parameters
                    if p in hints and p != "return"
                }
                try:
                    method(**kwargs)
                except (ValueError, TypeError, KeyError):
                    pass

            still_written = {}
            for filename, structure in STRUCTURE_MAP.items():
                path = tmp_path / filename
                if not path.exists():
                    continue
                payload = json.load(open(path))
                for key, entry_name in structure.items():
                    if key == "_root":
                        continue
                    for record in payload.get(key, []):
                        extra = set(record.keys()) - set(allowed[entry_name])
                        still_written.setdefault((filename, key), set()).update(extra)
                for stats in payload.get("task_patterns", {}).values():
                    extra = set(stats.keys()) - set(allowed["task_patterns"])
                    still_written.setdefault((filename, "task_patterns"), set()).update(extra)
        finally:
            _teardown_backend(patches, use_sqlite=False)

    for location, fields in sorted(KNOWN_JSON_DRIFT.items()):
        actual = still_written.get(location, set())
        fixed = fields - actual
        assert not fixed, (
            f"{location[0]}:{location[1]} no longer writes {sorted(fixed)} - remove it "
            "from KNOWN_JSON_DRIFT so the allowlist check stops excusing it"
        )
