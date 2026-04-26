"""
Pytest configuration for empathySync test suite.

Session-level setup that applies to all tests.
"""

import pytest


@pytest.fixture(autouse=True, scope="session")
def deterministic_ollama():
    """Pin Ollama's random seed so conversation quality tests produce identical
    output on every run for a given model version.

    Ollama's `seed` option makes sampling fully deterministic - same prompt +
    same seed + same model = same tokens every time. Without this, max_words
    assertions are inherently flaky because LLM output varies slightly between
    runs even at low temperature.

    OllamaClient reads settings.OLLAMA_SEED inside generate() (not cached at
    init), so patching the singleton here takes effect for all Ollama calls
    made during the test session.
    """
    from config.settings import settings

    original = settings.OLLAMA_SEED
    settings.OLLAMA_SEED = 42
    yield
    settings.OLLAMA_SEED = original
