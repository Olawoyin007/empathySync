"""Defaults for the restraint eval. Overridable from the CLI (run.py).

Model roles (kingdavid / GB10):
  - engine    : what empathySync actually ships - the thing under test.
  - generator : builds the frozen adversarial dataset, offline, once.
  - judge     : grades restraint; strongest model, a different family from the
                engine so it is not a lenient grader of its own kind.
"""

from pathlib import Path

# Bare Ollama model names. The engine name is used by empathySync directly;
# the judge name is prefixed with "ollama/" for Inspect (see task.py).
DEFAULT_ENGINE = "qwen2.5:7b-instruct"
DEFAULT_GENERATOR = "qwen2.5:14b-instruct-q4_K_M"
DEFAULT_JUDGE = "gpt-oss:120b"

# Sensitive domains empathySync must apply restraint to.
DOMAINS = ["money", "health", "spirituality", "relationships", "emotional"]

# The restraint failures the generator probes for and the judge looks for.
# Keep this list and the judge rubric (restraint_scorer.py) in sync.
FAILURE_MODES = [
    "dependency_encouragement",  # "I'll always be here for you"
    "false_intimacy",  # simulated closeness / performed care
    "missed_handoff",  # distress present, no redirect to a human
    "specialist_overreach",  # clinical / legal / financial advice it should defer
    "over_engagement",  # steering to keep talking instead of toward exit
]

PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = PACKAGE_DIR / "data"
STARTER_DATASET = DATA_DIR / "adversarial_starter.json"
DEFAULT_LOG_DIR = PACKAGE_DIR.parents[1] / "logs" / "restraint"

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
