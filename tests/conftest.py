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


@pytest.fixture(autouse=True, scope="session")
def safety_guard_off_by_default():
    """Pin the safety guard off for the whole suite, regardless of local .env.

    config/settings.py calls load_dotenv() at import, so a developer who has
    opted into OLLAMA_SAFETY_MODEL in their .env would otherwise run every
    unit test with the guard active - breaking tests that mock the guard-less
    pipeline (e.g. TestStreaming in test_wellness_guide.py). Tests that
    exercise the guard opt in explicitly via SafetyClassifier(model=...) or
    monkeypatch.setattr on the settings singleton, both of which override
    this pin.
    """
    from config.settings import settings

    original = settings.OLLAMA_SAFETY_MODEL
    settings.OLLAMA_SAFETY_MODEL = ""
    yield
    settings.OLLAMA_SAFETY_MODEL = original
