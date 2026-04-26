"""
OllamaClient — HTTP communication layer for Ollama API.

Extracted from WellnessGuide (Phase 16.8.2) to give a single,
focused class responsible for:
  - Non-streaming generation (`generate`)
  - Streaming generation (`generate_stream`)
  - Health checking (`check_health`)

All other concerns (prompt building, safety pipeline, session state)
remain in WellnessGuide and other components.
"""

import json
import time
import httpx
import logging
from typing import Generator

from config.settings import settings
from utils.scenario_loader import get_scenario_loader

logger = logging.getLogger(__name__)


class OllamaClient:
    """Thin HTTP wrapper around the Ollama /api/generate endpoint.

    Args:
        model: Ollama model name (default: from settings).
        temperature: Sampling temperature (default: from settings).
        http_client: Injectable httpx.Client for testability and connection reuse.
                     If None, uses the shared module-level client.
    """

    def __init__(
        self,
        model: str = None,
        temperature: float = None,
        http_client: httpx.Client = None,
    ):
        self._http_client = http_client
        self.ollama_url = f"{settings.OLLAMA_HOST}/api/generate"
        self.model = model or settings.OLLAMA_MODEL
        self.temperature = temperature if temperature is not None else settings.OLLAMA_TEMPERATURE

        # Load tunables from system_defaults.yaml (falls back to hardcoded defaults)
        loader = get_scenario_loader()
        self.practical_max_tokens = loader.get_default(
            "ollama", "practical_max_tokens", fallback=2000
        )
        self.reflective_max_tokens = loader.get_default(
            "ollama", "reflective_max_tokens", fallback=300
        )
        self.practical_timeout = loader.get_default(
            "ollama", "practical_timeout_seconds", fallback=120
        )
        self.reflective_timeout = loader.get_default(
            "ollama", "reflective_timeout_seconds", fallback=45
        )

    @property
    def http_client(self) -> httpx.Client:
        """Lazy-resolved HTTP client — injected or shared singleton."""
        if self._http_client is not None:
            return self._http_client
        from utils.http_client import get_http_client

        return get_http_client()

    def generate(self, prompt: str, is_practical: bool = False) -> str:
        """Send a prompt to Ollama and return the full response text.

        Args:
            prompt: The prompt to send.
            is_practical: If True, allows longer responses and timeout
                          for practical tasks (2000 tokens, 120s).
                          If False, uses brief settings (300 tokens, 45s).

        Returns:
            The model's response text, stripped of leading/trailing whitespace.

        Raises:
            Exception: If the Ollama API is unreachable or returns an error.
        """
        max_tokens = self.practical_max_tokens if is_practical else self.reflective_max_tokens
        timeout_seconds = self.practical_timeout if is_practical else self.reflective_timeout

        options: dict = {"temperature": self.temperature, "top_p": 0.9, "num_predict": max_tokens}
        if settings.OLLAMA_SEED is not None:
            options["seed"] = settings.OLLAMA_SEED

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }

        try:
            t_start = time.perf_counter()
            response = self.http_client.post(self.ollama_url, json=payload, timeout=timeout_seconds)
            response.raise_for_status()
            elapsed = time.perf_counter() - t_start

            result = response.json()
            text = result.get("response", "").strip()
            logger.info(
                "ollama.generate | model=%s | practical=%s | tokens=%d | duration_s=%.2f",
                self.model,
                is_practical,
                result.get("eval_count", 0),
                elapsed,
            )
            return text

        except httpx.HTTPError as e:
            logger.error(f"Ollama API error: {str(e)}")
            raise Exception(
                f"Unable to connect to Ollama. Please ensure it's running at {settings.OLLAMA_HOST}"
            )

    def generate_stream(
        self, prompt: str, is_practical: bool = False
    ) -> Generator[str, None, None]:
        """Stream tokens from Ollama, yielding each as it arrives.

        Args:
            prompt: The prompt to send.
            is_practical: If True, uses longer token limit and timeout.

        Yields:
            Individual non-empty tokens as they arrive from the model.
        """
        max_tokens = self.practical_max_tokens if is_practical else self.reflective_max_tokens
        timeout_seconds = self.practical_timeout if is_practical else self.reflective_timeout

        options: dict = {"temperature": self.temperature, "top_p": 0.9, "num_predict": max_tokens}
        if settings.OLLAMA_SEED is not None:
            options["seed"] = settings.OLLAMA_SEED

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": options,
        }

        try:
            t_start = time.perf_counter()
            t_first_token = None
            total_tokens = 0
            with self.http_client.stream(
                "POST", self.ollama_url, json=payload, timeout=timeout_seconds
            ) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = chunk.get("response", "")
                    if token:
                        if t_first_token is None:
                            t_first_token = time.perf_counter() - t_start
                        total_tokens += 1
                        yield token
                    if chunk.get("done"):
                        elapsed = time.perf_counter() - t_start
                        logger.info(
                            "ollama.stream | model=%s | practical=%s | tokens=%d | ttft_s=%.2f | duration_s=%.2f",
                            self.model,
                            is_practical,
                            total_tokens,
                            t_first_token or 0.0,
                            elapsed,
                        )
                        break

        except httpx.HTTPError as e:
            logger.error(f"Ollama streaming API error: {str(e)}")
            raise Exception(
                f"Unable to connect to Ollama. Please ensure it's running at {settings.OLLAMA_HOST}"
            )

    def check_health(self) -> bool:
        """Check if Ollama connection is healthy by sending a test prompt."""
        try:
            test_response = self.generate("Hello")
            return bool(test_response)
        except Exception:
            return False
