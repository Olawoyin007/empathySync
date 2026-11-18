"""
The five THREAT_MODEL.md controls that nothing was checking (issue #235).

`tests/test_threat_model_map.py` enforces that each control in the document
names a test. Five named `none`: they were real in the code and nothing proved
they stayed that way. This file is those five.

Two of them are runtime properties and are tested as such. Three can only be
checked at the boundary available to a unit test, and each says so in its own
docstring rather than implying more coverage than it has:

- no external calls          - runtime: every request goes to OLLAMA_HOST
- atomic writes              - runtime: a crash mid-write leaves the old file
- SQL name whitelists        - runtime: unknown table/column raises
- OLLAMA_HOST scheme check   - validator logic, not process startup
- non-root container         - file contract; running it needs Docker
"""

import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


# ===================== No external calls =====================


class TestNoExternalCalls:
    """
    Only outbound traffic is to the local OLLAMA_HOST.

    THREAT_MODEL.md: "No external calls | Only outbound traffic is to the local
    `OLLAMA_HOST`". Checked two ways: every request the pipeline actually makes
    is asserted against the configured host, and no module is allowed to build
    its own HTTP client, because that is how a call that skips the check would
    get added later.
    """

    # THREAT_MODEL.md control: No external calls
    def test_every_request_goes_to_the_configured_ollama_host(self):
        from config.settings import settings
        from models.llm_classifier import LLMClassifier

        seen = []

        def record(url, *args, **kwargs):
            seen.append(url)
            response = Mock()
            response.status_code = 200
            response.json.return_value = {"response": "{}"}
            return response

        client = Mock()
        client.post.side_effect = record
        with patch("utils.http_client.get_http_client", return_value=client):
            LLMClassifier()._call_ollama("a message")

        assert seen, "no request was made, so this asserted nothing"
        for url in seen:
            assert url.startswith(settings.OLLAMA_HOST), (
                f"request to {url!r} is outside OLLAMA_HOST ({settings.OLLAMA_HOST}) - "
                "all processing must remain local"
            )

    # THREAT_MODEL.md control: No external calls
    def test_only_the_shared_client_module_constructs_an_http_client(self):
        """A module with its own client could reach anywhere unobserved."""
        offenders = []
        for path in (REPO_ROOT / "src").rglob("*.py"):
            if path.name == "http_client.py":
                continue
            source = path.read_text()
            for pattern in (
                r"httpx\.Client\(",
                r"httpx\.AsyncClient\(",
                r"\brequests\.(get|post)\(",
            ):
                if re.search(pattern, source):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern}")
        assert not offenders, (
            "these bypass utils/http_client.get_http_client(), so outbound traffic "
            f"from them is unchecked: {offenders}"
        )


# ===================== SQL name whitelists =====================


class TestSQLNameWhitelists:
    """
    THREAT_MODEL.md: "No SQL injection via dynamic names | Table and column
    whitelists; all values parameterized".
    """

    # THREAT_MODEL.md control: No SQL injection via dynamic names
    def test_unknown_column_is_rejected(self):
        from utils.storage_backend import SQLiteBackend

        with pytest.raises(ValueError, match="Invalid column"):
            SQLiteBackend._validate_columns(
                SQLiteBackend, "trusted_people", {"name": "Sam", "injected": "x"}
            )

    # THREAT_MODEL.md control: No SQL injection via dynamic names
    def test_unknown_table_is_rejected(self):
        from utils.storage_backend import SQLiteBackend

        with pytest.raises(ValueError, match="No column whitelist"):
            SQLiteBackend._validate_columns(SQLiteBackend, "'; DROP TABLE --", {"a": 1})

    # THREAT_MODEL.md control: No SQL injection via dynamic names
    def test_every_method_building_sql_from_caller_keys_validates_first(self):
        """
        Only the update_* methods interpolate caller-supplied names into SQL;
        every other write uses literal column names, which is why most tables
        need no column whitelist. What must hold is that a method which does
        build SQL from a caller's dict validates it before doing so - a fourth
        such method added without the guard is the regression this catches.
        """
        source = (REPO_ROOT / "src/utils/storage_backend.py").read_text()
        unguarded = []
        for block in source.split("\n    def ")[1:]:
            name = block.split("(", 1)[0]
            body = block.split("\n    def ", 1)[0]
            builds_sql_from_keys = 'f"{key} = ?"' in body or 'f"{k} = ?"' in body
            if builds_sql_from_keys and "_validate_columns(" not in body:
                unguarded.append(name)
        assert not unguarded, (
            f"{unguarded} build SQL from caller-supplied keys without calling "
            "_validate_columns first"
        )

    # THREAT_MODEL.md control: No SQL injection via dynamic names
    def test_every_validated_table_has_a_column_whitelist(self):
        """A _validate_columns call naming a table with no whitelist raises at use time."""
        from utils.storage_backend import SQLiteBackend

        source = (REPO_ROOT / "src/utils/storage_backend.py").read_text()
        named = set(re.findall(r'_validate_columns\(\s*"([a-z_]+)"', source))
        assert named, "no _validate_columns call sites found - the parser matched nothing"
        missing = named - set(SQLiteBackend._VALID_COLUMNS)
        assert not missing, f"validated at runtime but no whitelist defined: {sorted(missing)}"

    # THREAT_MODEL.md control: No SQL injection via dynamic names
    def test_every_interpolated_table_name_is_checked_or_literal(self):
        """
        Three sites interpolate a table name into SQL. Each must either check it
        against _VALID_TABLES or iterate a hardcoded list; a name arriving from
        anywhere else would be an injection surface.
        """
        source = (REPO_ROOT / "src/utils/storage_backend.py").read_text()
        lines = source.split("\n")
        sites = [
            i for i, line in enumerate(lines) if re.search(r'execute\(\s*f"[^"]*\{table\}', line)
        ]
        assert sites, "no interpolated table names found - the parser matched nothing"
        for i in sites:
            preceding = "\n".join(lines[max(0, i - 6) : i])
            checked = "_VALID_TABLES" in preceding
            literal = re.search(r'for table in \[\s*"', preceding) is not None
            assert checked or literal, (
                f"line {i + 1} interpolates a table name that is neither checked "
                f"against _VALID_TABLES nor drawn from a literal list:\n{lines[i].strip()}"
            )


# ===================== OLLAMA_HOST scheme check =====================


class TestOllamaHostValidation:
    """
    THREAT_MODEL.md: "`OLLAMA_HOST` validation | http(s) scheme checked at config
    load".

    This exercises the validator, not process startup: the settings fields are
    read from the environment once at import, so a test cannot re-run that
    without reimporting the module. `validate_config()` is where the rule lives.
    """

    @pytest.mark.parametrize(
        "host",
        ["file:///etc/passwd", "ftp://example.com", "ollama://localhost", "localhost:11434", ""],
    )
    # THREAT_MODEL.md control: `OLLAMA_HOST` validation
    def test_a_non_http_host_is_reported(self, host):
        from config.settings import Settings

        s = Settings()
        s.OLLAMA_HOST = host
        assert any(
            "OLLAMA_HOST" in e for e in s.validate_config()
        ), f"{host!r} passed validation - only http:// and https:// are acceptable"

    @pytest.mark.parametrize("host", ["http://localhost:11434", "https://ollama.internal"])
    # THREAT_MODEL.md control: `OLLAMA_HOST` validation
    def test_an_http_host_passes(self, host):
        from config.settings import Settings

        s = Settings()
        s.OLLAMA_HOST = host
        s.OLLAMA_MODEL = "a-model"
        assert s.validate_config() == []


# ===================== Atomic writes =====================


class TestAtomicWrites:
    """
    THREAT_MODEL.md: "Atomic writes | `mkstemp` + `fsync` + `os.replace` (no torn
    files on crash)". The property that matters is the outcome, so the test
    interrupts the write rather than asserting which calls were made.
    """

    def _json_backend(self, tmp_path):
        import utils.database as db_module
        from utils.storage_backend import get_storage_backend, reset_storage_backend

        db_module._connection = None
        db_module._db_path = None
        reset_storage_backend()
        patches = [
            patch(f"{m}.settings")
            for m in ("utils.storage_backend", "utils.database", "config.settings")
        ]
        for mock in [p.start() for p in patches]:
            mock.DATA_DIR = tmp_path
            mock.USE_SQLITE = False
            mock.ENABLE_DEVICE_LOCK = False
            mock.DATA_RETENTION_DAYS = 90
        return get_storage_backend(), patches

    # THREAT_MODEL.md control: Atomic writes
    def test_a_crash_mid_write_leaves_the_previous_file_intact(self):
        from utils.storage_backend import reset_storage_backend

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            backend, patches = self._json_backend(tmp_path)
            try:
                backend.add_check_in(3, notes="the good record")
                before = (tmp_path / "wellness_data.json").read_text()

                with patch("os.replace", side_effect=OSError("crash")):
                    with pytest.raises(OSError):
                        backend.add_check_in(4, notes="the interrupted record")

                after = (tmp_path / "wellness_data.json").read_text()
                assert after == before, "an interrupted write changed the live file"
                leftovers = list(tmp_path.glob(".wellness_*.tmp"))
                assert not leftovers, f"temp files left behind after a failed write: {leftovers}"
            finally:
                reset_storage_backend()
                for p in patches:
                    p.stop()

    # THREAT_MODEL.md control: Atomic writes
    def test_the_target_file_is_never_opened_for_writing_directly(self):
        """
        Writing in place is what makes a torn file possible, so the save paths
        must go through a temp file. mkstemp + fsync + os.replace is the shape
        the threat model claims; this asserts the claim against the source.
        """
        source = (REPO_ROOT / "src/utils/storage_backend.py").read_text()
        for name in ("_save_wellness", "_save_network"):
            body = source.split(f"def {name}(", 1)[1].split("\n    def ", 1)[0]
            assert "mkstemp" in body, f"{name} does not write via a temp file"
            assert "os.fsync" in body, f"{name} does not fsync before replacing"
            assert "os.replace" in body, f"{name} does not swap the file atomically"


# ===================== Non-root container =====================


class TestNonRootContainer:
    """
    THREAT_MODEL.md: "Non-root container | `gosu` drops root to `PUID:PGID`;
    Ollama bound to `127.0.0.1`".

    A file contract, not a runtime test. Proving the running container is
    unprivileged needs Docker, which CI does not have here; what this catches is
    the privilege drop or the loopback binding being edited away.
    """

    # THREAT_MODEL.md control: Non-root container
    def test_the_entrypoint_drops_root_to_puid_pgid(self):
        entrypoint = (REPO_ROOT / "docker/entrypoint.sh").read_text()
        assert "gosu" in entrypoint, "entrypoint no longer drops privileges with gosu"
        assert re.search(r'PUID="\$\{PUID:-\d+\}"', entrypoint), "PUID default is gone"
        assert re.search(r'PGID="\$\{PGID:-\d+\}"', entrypoint), "PGID default is gone"
        assert re.search(
            r'exec\s+gosu\s+"?\$PUID', entrypoint
        ), "the app is not exec'd through gosu, so it may still run as root"

    # THREAT_MODEL.md control: Non-root container
    def test_ollama_is_published_only_on_loopback(self):
        compose = (REPO_ROOT / "docker-compose.yml").read_text()
        assert '"127.0.0.1:11434:11434"' in compose, (
            "the Ollama port is no longer pinned to loopback - it would be reachable "
            "from the network"
        )
