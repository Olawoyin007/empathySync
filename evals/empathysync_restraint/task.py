"""The Inspect Task: empathySync pipeline + restraint judge over the dataset."""

from __future__ import annotations

from inspect_ai import Task, task

from .config import DEFAULT_ENGINE, DEFAULT_JUDGE, STARTER_DATASET
from .dataset import load_dataset
from .pipeline_solver import empathysync_pipeline
from .restraint_scorer import restraint_scorer


@task
def empathysync_restraint(
    dataset_path: str = str(STARTER_DATASET),
    engine: str = DEFAULT_ENGINE,
    judge: str = DEFAULT_JUDGE,
    ollama_host: str = "",
) -> Task:
    """Run adversarial prompts through empathySync and grade its restraint.

    Args:
        dataset_path: JSON dataset of adversarial cases.
        engine: Ollama model empathySync runs as its engine (the thing tested).
        judge: Ollama model that grades restraint (prefixed for Inspect here).
        ollama_host: override for the Ollama base URL.
    """
    return Task(
        dataset=load_dataset(dataset_path),
        solver=empathysync_pipeline(engine, ollama_host),
        scorer=restraint_scorer(f"ollama/{judge}"),
        # The solver never calls this model (it drives the pipeline directly);
        # it is set so Inspect resolves a model, and matches the grader.
        model=f"ollama/{judge}",
        # A few sample errors should not abort a long run.
        fail_on_error=0.2,
    )
