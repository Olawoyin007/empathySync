"""Preflight guard - run before any eval touches the models.

On a unified-memory system, over-committing RAM can hang or hard-reboot the
whole host rather than just killing one process. So we refuse to start unless
the models exist and there is real headroom. Read-only and cheap.

The budget is weights *plus* KV cache. Ollama reserves the KV cache at load
time, sized by context x parallel slots, and for a small model with a long
default context it can dwarf the weights (#247: a 1.3G guard model asked for
tens of GB). A budget that counts weights alone passes, the load then dies, and
the pipeline falls back to keyword-only classification - correctly and
silently. So the estimate errs high: over-estimating costs a request to free
memory, under-estimating costs a quietly wrong safety number.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

# Ollama's KV cache is f16 unless OLLAMA_KV_CACHE_TYPE says otherwise. q8_0 and
# q4_0 are smaller, so assuming f16 can only over-estimate - which is the safe side.
KV_BYTES_PER_ELEMENT = 2

# Ollama's own default for OLLAMA_MAX_LOADED_MODELS on a CPU / unified-memory host.
DEFAULT_MAX_LOADED_MODELS = 3


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
    """Model names Ollama currently holds in memory (roommates in the shared pool)."""
    try:
        r = httpx.get(f"{host}/api/ps", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except httpx.HTTPError:
        return []


def show(host: str, model: str) -> dict:
    """Ollama's /api/show for one model: `model_info` metadata and baked `parameters`.

    Returns {} if the server cannot describe the model; the caller then cannot
    size that model's KV cache and says so rather than guessing.
    """
    try:
        r = httpx.post(f"{host}/api/show", json={"model": model}, timeout=10)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPError:
        return {}


def env_int(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back to `default`."""
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def resolve_slots(override: int | None = None) -> tuple[int, str]:
    """The parallel slot count to size the KV cache for, and where it came from.

    Ollama reserves KV cache per slot, so this multiplies every estimate. The
    server's value is not visible over the API: an explicit override wins, then
    OLLAMA_NUM_PARALLEL in *this* shell, then 1. This shell can disagree with
    the server (#247: the service set 4 in a systemd drop-in while the eval saw
    nothing), so callers print the result on every run, pass or fail.
    """
    if override is not None and override > 0:
        return override, "--num-parallel"
    raw = os.getenv("OLLAMA_NUM_PARALLEL", "")
    value = env_int("OLLAMA_NUM_PARALLEL", 0)
    if value:
        return value, "OLLAMA_NUM_PARALLEL in this shell"
    if raw.strip() == "0":
        # 0 is Ollama's "you decide", not a mistake; naming it invalid would send
        # someone chasing a setting that is doing its job.
        return 1, "OLLAMA_NUM_PARALLEL=0 in this shell, which is Ollama's auto; assuming 1"
    if raw:
        return 1, f"default; ignored invalid OLLAMA_NUM_PARALLEL={raw!r}"
    return 1, "default; OLLAMA_NUM_PARALLEL is not set in this shell"


def resolve_max_loaded(override: int | None = None) -> tuple[int | None, str]:
    """How many models Ollama keeps resident, and where that number came from.

    None means this shell cannot see the value. Like OLLAMA_NUM_PARALLEL, the
    service can set it in a systemd drop-in the eval never sees, so an unknown
    value is reported as an assumption rather than warned about: a warning that
    fires on every run is one nobody reads.
    """
    if override is not None and override > 0:
        return override, "--max-loaded"
    value = env_int("OLLAMA_MAX_LOADED_MODELS", 0)
    if value:
        return value, "OLLAMA_MAX_LOADED_MODELS in this shell"
    return None, f"not set in this shell; Ollama defaults to {DEFAULT_MAX_LOADED_MODELS}"


def kv_bytes_per_token(model_info: dict) -> int | None:
    """KV-cache bytes one token of context costs, from /api/show `model_info`.

    2 (K and V) x block_count x head_count_kv x head_dim x bytes_per_element,
    with K and V head sizes read separately where the model declares them.
    `head_count_kv` may be one number or a per-layer list (some architectures
    vary it by layer); a list is summed, which is the same product per layer.
    Returns None when the metadata needed is missing.
    """
    arch = model_info.get("general.architecture")
    if not arch:
        return None
    blocks = model_info.get(f"{arch}.block_count")
    kv_heads = model_info.get(f"{arch}.attention.head_count_kv")
    heads = model_info.get(f"{arch}.attention.head_count")
    embd = model_info.get(f"{arch}.embedding_length")

    # Head size: declared key/value lengths, else embedding_length / head_count.
    fallback_dim = None
    if isinstance(heads, int) and heads > 0 and isinstance(embd, int):
        fallback_dim = embd // heads
    k_dim = model_info.get(f"{arch}.attention.key_length") or fallback_dim
    v_dim = model_info.get(f"{arch}.attention.value_length") or k_dim

    if not blocks or not k_dim or not v_dim:
        return None
    if isinstance(kv_heads, list):
        kv_head_layers = sum(kv_heads)
    else:
        # Older GGUFs omit head_count_kv when it equals head_count (no GQA).
        kv_heads = kv_heads or heads
        if not isinstance(kv_heads, int) or kv_heads <= 0:
            return None
        kv_head_layers = blocks * kv_heads
    return kv_head_layers * (k_dim + v_dim) * KV_BYTES_PER_ELEMENT


def baked_num_ctx(parameters: str) -> int | None:
    """`num_ctx` from a model's baked Modelfile parameters, if it sets one."""
    for line in (parameters or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "num_ctx":
            try:
                return int(parts[1])
            except ValueError:
                return None
    return None


@dataclass
class KVEstimate:
    model: str
    bytes_per_token: int
    num_ctx: int
    ctx_source: str
    slots: int

    @property
    def total_bytes(self) -> int:
        return self.bytes_per_token * self.num_ctx * self.slots

    def explain(self) -> str:
        return (
            f"{self.model} reserves ~{self.total_bytes / 1e9:.1f}G of KV cache = "
            f"{self.num_ctx} ctx ({self.ctx_source}) x {self.slots} slot(s) "
            f"x {self.bytes_per_token} B/token"
        )


def estimate_kv(
    model: str,
    info: dict,
    slots: int,
    sent_num_ctx: int | None = None,
) -> KVEstimate | None:
    """Size one model's KV reservation, or None if its metadata is incomplete.

    The context Ollama reserves is the first of: what the caller sends, what
    the model bakes into its own parameters, or the model's trained length.
    """
    model_info = info.get("model_info") or {}
    per_token = kv_bytes_per_token(model_info)
    if per_token is None:
        return None

    baked = baked_num_ctx(info.get("parameters", ""))
    arch = model_info.get("general.architecture")
    trained = model_info.get(f"{arch}.context_length")
    if sent_num_ctx:
        num_ctx, source = sent_num_ctx, "OLLAMA_NUM_CTX"
    elif baked:
        num_ctx, source = baked, "baked into the model"
    elif trained:
        num_ctx, source = trained, "model default context_length"
    else:
        return None
    return KVEstimate(model, per_token, num_ctx, source, slots)


def preflight(
    host: str,
    required_models: list[str],
    headroom_gb: float = 8.0,
    num_ctx_by_model: dict[str, int] | None = None,
    num_parallel: int | None = None,
    max_loaded: int | None = None,
) -> tuple[list[str], list[str]]:
    """Return (fatals, warnings). A non-empty `fatals` means: do not start.

    `num_ctx_by_model` is the context the caller will send per model, for the
    models whose requests carry one (the empathySync pipeline does when
    OLLAMA_NUM_CTX is set; the judge, called through Inspect, does not).
    `num_parallel` overrides the slot count; see `resolve_slots`.
    `max_loaded` overrides the resident-model limit; see `resolve_max_loaded`.
    """
    fatals: list[str] = []
    warnings: list[str] = []
    num_ctx_by_model = num_ctx_by_model or {}
    distinct = list(dict.fromkeys(required_models))

    try:
        installed = tags(host)
    except httpx.HTTPError as e:
        return ([f"Ollama not reachable at {host}: {e}"], [])

    missing = [m for m in distinct if m not in installed]
    if missing:
        for m in missing:
            fatals.append(f"model not installed: {m}  (run: ollama pull {m})")
        return (fatals, warnings)

    slots, slot_source = resolve_slots(num_parallel)

    weights_gb = sum(installed[m] for m in distinct) / 1e9
    estimates: list[KVEstimate] = []
    for m in distinct:
        est = estimate_kv(m, show(host, m), slots, num_ctx_by_model.get(m))
        if est is None:
            warnings.append(
                f"could not size the KV cache for {m} (no usable /api/show metadata); "
                f"the memory check counts its weights only."
            )
        else:
            estimates.append(est)
    kv_gb = sum(e.total_bytes for e in estimates) / 1e9

    # The resident budget is weights plus the KV cache Ollama reserves at load.
    need_gb = weights_gb + kv_gb
    avail, free = read_meminfo_gb()
    if avail < need_gb + headroom_gb:
        lines = [
            f"not enough memory: models need ~{need_gb:.0f}G "
            f"(weights {weights_gb:.0f}G + KV cache {kv_gb:.0f}G) + {headroom_gb:.0f}G "
            f"headroom, only {avail:.0f}G available. Free memory first "
            f"(check: ollama ps; free -h)."
        ]
        for est in sorted(estimates, key=lambda e: e.total_bytes, reverse=True):
            lines.append(f"  {est.explain()}")
        lines.append(
            f"  Sized for {slots} parallel slot(s) ({slot_source}). If the ollama "
            f"service runs a different number, pass --num-parallel N."
        )
        if estimates:
            lines.append(
                "  To shrink the KV cache: set OLLAMA_NUM_CTX, or lower OLLAMA_NUM_PARALLEL "
                "on the ollama service."
            )
        fatals.append("\n".join(lines))
    elif free < need_gb + headroom_gb:
        warnings.append(
            f"only {free:.0f}G is truly free (page cache holds the rest); "
            f"a large model load may still be tight."
        )

    # Too few load slots does not fail: Ollama evicts and reloads mid-run, so a
    # large judge is reloaded every sample and the run effectively never finishes.
    # Only warn on a value this shell can actually see: assuming the default and
    # warning on it fired on every run of a correctly configured box (#248).
    loaded, loaded_source = resolve_max_loaded(max_loaded)
    if loaded is not None and loaded < len(distinct):
        warnings.append(
            f"OLLAMA_MAX_LOADED_MODELS is {loaded} ({loaded_source}) but this run "
            f"needs {len(distinct)} models resident ({', '.join(distinct)}). Ollama "
            f"will evict and reload between calls; set "
            f"OLLAMA_MAX_LOADED_MODELS>={len(distinct)} on the ollama service."
        )

    others = [m for m in resident(host) if m not in set(distinct)]
    if others:
        warnings.append(
            "other models resident in the same memory pool right now: "
            + ", ".join(others)
            + " (they share the same memory pool; consider `ollama stop` if memory is tight)."
        )

    return (fatals, warnings)
