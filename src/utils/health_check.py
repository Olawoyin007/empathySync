"""
Startup health checks for empathySync.

Validates that all dependencies are available before the app launches:
- Ollama server reachable
- Required model downloaded
- Data directory writable
- SQLite database accessible (if enabled)
"""

import logging
import httpx
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from config.settings import settings
from utils.http_client import get_http_client

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Result of a single health check."""

    name: str
    ok: bool
    message: str
    critical: bool = True  # If True, blocks app startup
    details: Optional[str] = None


def check_ollama_server() -> HealthStatus:
    """Check if Ollama server is reachable."""
    try:
        client = get_http_client()
        response = client.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=5)
        if response.status_code == 200:
            return HealthStatus(name="Ollama Server", ok=True, message="Connected")
        else:
            return HealthStatus(
                name="Ollama Server",
                ok=False,
                message=f"Ollama returned status {response.status_code}",
                details=f"URL: {settings.OLLAMA_HOST}",
            )
    except httpx.ConnectError:
        return HealthStatus(
            name="Ollama Server",
            ok=False,
            message="Cannot connect to Ollama",
            details=(
                f"Tried: {settings.OLLAMA_HOST}\n\n"
                "**To fix:**\n"
                "1. Install Ollama: `curl -fsSL https://ollama.com/install.sh | sh`\n"
                "2. Start the server: `ollama serve`\n"
                "3. Verify it's running: `curl http://localhost:11434/api/tags`"
            ),
        )
    except httpx.TimeoutException:
        return HealthStatus(
            name="Ollama Server",
            ok=False,
            message="Ollama connection timed out",
            details=f"Server at {settings.OLLAMA_HOST} did not respond within 5 seconds",
        )
    except Exception as e:
        return HealthStatus(
            name="Ollama Server",
            ok=False,
            message=f"Unexpected error: {e}",
            details=f"URL: {settings.OLLAMA_HOST}",
        )


def check_ollama_model() -> HealthStatus:
    """Check if the configured model is available in Ollama.

    If the configured model is missing but other models are installed,
    automatically falls back to an available model so the app can start.
    """
    model_name = settings.OLLAMA_MODEL
    try:
        client = get_http_client()
        response = client.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=5)
        if response.status_code != 200:
            return HealthStatus(
                name="Ollama Model",
                ok=False,
                message="Cannot check models (server issue)",
                details="Fix the Ollama server connection first",
            )

        data = response.json()
        available_models = [m.get("name", "") for m in data.get("models", [])]
        # Check exact match or match without tag (e.g., "llama2" matches "llama2:latest")
        model_found = any(
            m == model_name or m.startswith(f"{model_name}:") for m in available_models
        )

        if model_found:
            return HealthStatus(name="Ollama Model", ok=True, message=f"`{model_name}` available")

        # Model not found - try to fallback to an available model
        if available_models:
            fallback = available_models[0]
            settings.OLLAMA_MODEL = fallback
            logger.warning(f"Model '{model_name}' not found, falling back to '{fallback}'")
            model_list = ", ".join(available_models[:5])
            return HealthStatus(
                name="Ollama Model",
                ok=True,
                message=f"Using `{fallback}` (configured `{model_name}` not found)",
                critical=False,
                details=(
                    f"Auto-selected from available: {model_list}\n\n"
                    f"To use your preferred model: `ollama pull {model_name}`"
                ),
            )

        # No models at all
        return HealthStatus(
            name="Ollama Model",
            ok=False,
            message="No models installed",
            details=(
                "Ollama is running but has no models.\n\n"
                "**To fix:**\n"
                f"`ollama pull {model_name}`"
            ),
        )
    except Exception:
        return HealthStatus(
            name="Ollama Model",
            ok=False,
            message="Cannot check model availability",
            details="Fix the Ollama server connection first",
        )


def check_data_directory() -> HealthStatus:
    """Check if the data directory exists and is writable."""
    data_dir = settings.DATA_DIR
    try:
        data_dir.mkdir(exist_ok=True)
        # Test write permission
        test_file = data_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        return HealthStatus(name="Data Directory", ok=True, message=f"`{data_dir}`", critical=True)
    except PermissionError:
        return HealthStatus(
            name="Data Directory",
            ok=False,
            message=f"No write permission to `{data_dir}`",
            critical=True,
            details="empathySync needs write access to store local data",
        )
    except Exception as e:
        return HealthStatus(name="Data Directory", ok=False, message=f"Error: {e}", critical=True)


def check_sqlite_database() -> HealthStatus:
    """Check SQLite database accessibility (only when USE_SQLITE=true)."""
    if not settings.USE_SQLITE:
        return HealthStatus(
            name="SQLite Database", ok=True, message="Not enabled (using JSON)", critical=False
        )

    db_path = settings.DATA_DIR / "empathySync.db"
    try:
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("SELECT 1")
        conn.close()
        return HealthStatus(
            name="SQLite Database", ok=True, message=f"`{db_path.name}`", critical=True
        )
    except Exception as e:
        return HealthStatus(
            name="SQLite Database",
            ok=False,
            message=f"Database error: {e}",
            critical=True,
            details=f"Path: {db_path}",
        )


def run_health_checks() -> List[HealthStatus]:
    """Run all startup health checks and return results."""
    checks = [
        check_ollama_server(),
        check_ollama_model(),
        check_data_directory(),
    ]

    # Only check SQLite if enabled
    if settings.USE_SQLITE:
        checks.append(check_sqlite_database())

    # Log results
    for check in checks:
        if check.ok:
            logger.info(f"Health check passed: {check.name} - {check.message}")
        else:
            level = logging.ERROR if check.critical else logging.WARNING
            logger.log(level, f"Health check failed: {check.name} - {check.message}")

    return checks


def has_critical_failures(checks: List[HealthStatus]) -> bool:
    """Check if any critical health checks failed."""
    return any(not c.ok and c.critical for c in checks)


def auto_pull_model(model_name: str) -> bool:
    """Pull a model from Ollama. Returns True on success.

    Uses the Ollama /api/pull endpoint which streams progress.
    This is a blocking call that may take several minutes.
    """
    try:
        client = get_http_client()
        # Use stream=True so we don't timeout on large downloads
        with client.stream(
            "POST",
            f"{settings.OLLAMA_HOST}/api/pull",
            json={"name": model_name},
            timeout=600,  # 10 min max for model download
        ) as response:
            if response.status_code != 200:
                return False
            # Consume the stream (Ollama sends progress JSON lines)
            for _line in response.iter_lines():
                pass
        # Verify the model is now available
        verify = client.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=5)
        if verify.status_code == 200:
            models = [m.get("name", "") for m in verify.json().get("models", [])]
            return any(m == model_name or m.startswith(f"{model_name}:") for m in models)
        return False
    except Exception as e:
        logger.error(f"Auto-pull failed for {model_name}: {e}")
        return False
