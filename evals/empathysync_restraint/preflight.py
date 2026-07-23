"""Preflight guard - run before any eval touches the models.

Mirrors the discipline of the vLLM switcher on this box: on unified memory an
over-commit does not kill a process, it reboots the machine. So we refuse to
start unless the models exist and there is real headroom. Read-only and cheap.
"""

from __future__ import annotations

import httpx


def read_meminfo_gb() -> tuple[float, float]:
    """Return (MemAvailable, MemFree) in GB from /proc/meminfo."""
    avail = free = 0.0
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable:"):
                avail = int(line.split()[1]) / 1048576
            elif line.startswith("MemFree:"):
                free = int(line.split()[1]) / 1048576
    return avail, free


def tags(host: str) -> dict[str, int]:
    """Map installed Ollama model name -> disk size (bytes). Raises on no server."""
    r = httpx.get(f"{host}/api/tags", timeout=10)
    r.raise_for_status()
    return {m["name"]: m.get("size", 0) for m in r.json().get("models", [])}


def resident(host: str) -> list[str]:
    """Model names Ollama currently holds in memory (roommates in the 119G pool)."""
    try:
        r = httpx.get(f"{host}/api/ps", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except httpx.HTTPError:
        return []


def preflight(
    host: str, required_models: list[str], headroom_gb: float = 8.0
) -> tuple[list[str], list[str]]:
    """Return (fatals, warnings). A non-empty `fatals` means: do not start."""
    fatals: list[str] = []
    warnings: list[str] = []

    try:
        installed = tags(host)
    except httpx.HTTPError as e:
        return ([f"Ollama not reachable at {host}: {e}"], [])

    missing = [m for m in required_models if m not in installed]
    if missing:
        for m in missing:
            fatals.append(f"model not installed: {m}  (run: ollama pull {m})")
        return (fatals, warnings)

    # Sum the distinct required models' sizes; that is the resident budget.
    need_gb = sum(installed[m] for m in set(required_models)) / 1e9
    avail, free = read_meminfo_gb()
    if avail < need_gb + headroom_gb:
        fatals.append(
            f"not enough memory: models need ~{need_gb:.0f}G + {headroom_gb:.0f}G "
            f"headroom, only {avail:.0f}G available. Free memory first "
            f"(check: ollama ps; free -h)."
        )
    elif free < need_gb + headroom_gb:
        warnings.append(
            f"only {free:.0f}G is truly free (page cache holds the rest); "
            f"a large model load may still be tight."
        )

    others = [m for m in resident(host) if m not in set(required_models)]
    if others:
        warnings.append(
            "other models resident in the same memory pool right now: "
            + ", ".join(others)
            + " (they share the 119G; consider `ollama stop` if memory is tight)."
        )

    return (fatals, warnings)
