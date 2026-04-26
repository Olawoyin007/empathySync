"""
empathySync Configuration Settings
Leveraging environment variables for secure configuration management
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Settings:
    """Application configuration settings"""

    # Application
    APP_NAME: str = "empathySync"
    APP_VERSION: str = "1.9.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Server
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("STREAMLIT_SERVER_PORT", "8501"))

    # Database (leveraging PostgreSQL)
    DB_HOST: str = os.getenv("DB_HOST", "")
    DB_PORT: Optional[int] = int(os.getenv("DB_PORT", "5432")) if os.getenv("DB_PORT") else None
    DB_NAME: str = os.getenv("DB_NAME", "")
    DB_USER: str = os.getenv("DB_USER", "")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

    @property
    def database_url(self) -> Optional[str]:
        """Construct database URL from components"""
        if not all([self.DB_HOST, self.DB_PORT, self.DB_NAME, self.DB_USER, self.DB_PASSWORD]):
            return None
        return f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # Ollama Configuration
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "")
    OLLAMA_TEMPERATURE: float = (
        float(os.getenv("OLLAMA_TEMPERATURE", "0.7")) if os.getenv("OLLAMA_TEMPERATURE") else 0.7
    )

    # Optional fixed seed for Ollama generation (makes output deterministic).
    # Set OLLAMA_SEED=42 in test environments to eliminate LLM non-determinism.
    OLLAMA_SEED: Optional[int] = int(os.getenv("OLLAMA_SEED")) if os.getenv("OLLAMA_SEED") else None

    # Dedicated classifier model (optional)
    # Uses a smaller, faster model for classification while the main model handles responses.
    # Falls back to OLLAMA_MODEL if not set. Recommended: mistral:7b-instruct
    OLLAMA_CLASSIFIER_MODEL: str = os.getenv("OLLAMA_CLASSIFIER_MODEL", "")

    # LLM Classification (Phase 9)
    # When enabled, uses the Ollama model to intelligently classify messages
    # instead of relying solely on keyword matching
    LLM_CLASSIFICATION_ENABLED: bool = (
        os.getenv("LLM_CLASSIFICATION_ENABLED", "true").lower() == "true"
    )

    # Storage Backend (Phase 11)
    # When enabled, uses SQLite instead of JSON for data storage
    # SQLite provides better concurrent access, transactions, and partial updates
    USE_SQLITE: bool = os.getenv("USE_SQLITE", "false").lower() == "true"

    # Device Lock (Phase 11)
    # When enabled, prevents data conflicts when syncing between devices
    # Uses heartbeat-based lock with 5-minute stale detection
    ENABLE_DEVICE_LOCK: bool = os.getenv("ENABLE_DEVICE_LOCK", "false").lower() == "true"

    # Lock file stale timeout in seconds (default: 5 minutes)
    LOCK_STALE_TIMEOUT: int = int(os.getenv("LOCK_STALE_TIMEOUT", "300"))

    # Privacy & Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-key-change-in-production")
    ENABLE_ANALYTICS: bool = os.getenv("ENABLE_ANALYTICS", "false").lower() == "true"
    STORE_CONVERSATIONS: bool = os.getenv("STORE_CONVERSATIONS", "true").lower() == "true"
    CONVERSATION_RETENTION_DAYS: int = int(os.getenv("CONVERSATION_RETENTION_DAYS", "30"))

    # Data Retention
    # Session data, check-ins, and policy events older than this are pruned on startup
    DATA_RETENTION_DAYS: int = int(os.getenv("DATA_RETENTION_DAYS", "90"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "empathysync.log")

    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    LOGS_DIR: Path = BASE_DIR / "logs"

    def __init__(self):
        """Ensure required directories exist"""
        self.DATA_DIR.mkdir(exist_ok=True)
        self.LOGS_DIR.mkdir(exist_ok=True)

    def validate_config(self) -> list[str]:
        """Validate configuration and return list of missing required settings"""
        missing = []

        if not self.OLLAMA_HOST:
            missing.append("OLLAMA_HOST")
        if not self.OLLAMA_MODEL:
            missing.append("OLLAMA_MODEL")

        # Database validation only if any DB setting is provided
        if any([self.DB_HOST, self.DB_NAME, self.DB_USER, self.DB_PASSWORD]):
            if not self.DB_HOST:
                missing.append("DB_HOST")
            if not self.DB_NAME:
                missing.append("DB_NAME")
            if not self.DB_USER:
                missing.append("DB_USER")
            if not self.DB_PASSWORD:
                missing.append("DB_PASSWORD")

        return missing


# Global settings instance
settings = Settings()
