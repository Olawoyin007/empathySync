"""Load the frozen adversarial dataset into Inspect Samples.

The dataset is generated once (generate_dataset.py) and frozen, so runs are
reproducible and we are not overfitting empathySync to a moving generator
(Apollo: a benchmark should "interact with the model as little as possible").
"""

from __future__ import annotations

import json
from pathlib import Path

from inspect_ai.dataset import Sample


def load_dataset(path: str | Path) -> list[Sample]:
    """Read a JSON list of {id, domain, failure_mode, prompt} into Samples.

    `target` is the constant "restraint" - the ideal behaviour. The real
    grading is intrinsic (the rubric in restraint_scorer.py), so domain and
    failure_mode travel in metadata for the judge and the logs.
    """
    records = json.loads(Path(path).read_text())
    samples: list[Sample] = []
    for i, rec in enumerate(records):
        samples.append(
            Sample(
                id=rec.get("id", f"case-{i:04d}"),
                input=rec["prompt"],
                target="restraint",
                metadata={
                    "domain": rec.get("domain"),
                    "failure_mode": rec.get("failure_mode"),
                },
            )
        )
    return samples
