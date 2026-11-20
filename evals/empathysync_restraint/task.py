"""The Inspect Task: empathySync pipeline + restraint judge over the dataset."""

from __future__ import annotations

from inspect_ai import Task, task

from .config import DEFAULT_ENGINE, DEFAULT_JUDGE, STARTER_DATASET
from .dataset import load_dataset
from .domain_scorer import domain_scorer
from .pipeline_solver import bare_engine, empathysync_classify_only, empathysync_pipeline
from .practical_scorer import practical_scorer
from .restraint_scorer import restraint_scorer


def _grader(grade: str, judge: str):
    """Pick the rubric. Both judged arms take the same choice, because an
    ablation is only an ablation if the two arms are graded identically."""
    build = practical_scorer if grade == "practical" else restraint_scorer
    return build(f"ollama/{judge}")


@task
def empathysync_restraint(
    dataset_path: str = str(STARTER_DATASET),
    engine: str = DEFAULT_ENGINE,
    judge: str = DEFAULT_JUDGE,
    ollama_host: str = "",
    temperature: float = 0.0,
    grade: str = "restraint",
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
        solver=empathysync_pipeline(engine, ollama_host, temperature),
        scorer=_grader(grade, judge),
        # The solver never calls this model (it drives the pipeline directly);
        # it is set so Inspect resolves a model, and matches the grader.
        model=f"ollama/{judge}",
        # A few sample errors should not abort a long run.
        fail_on_error=0.2,
    )


@task
def empathysync_domain(
    dataset_path: str = str(STARTER_DATASET),
    engine: str = DEFAULT_ENGINE,
    ollama_host: str = "",
) -> Task:
    """Classifier side (mode 2): did the pipeline route each adversarial prompt
    into a restraint-triggering domain? Rule-based grading, no judge model - so
    it runs on modest hardware (only the engine, classifier, and safety models
    load; not the 65 GB restraint judge).

    Args:
        dataset_path: JSON dataset of adversarial cases.
        engine: Ollama model empathySync runs as its engine (the thing tested).
        ollama_host: override for the Ollama base URL.
    """
    return Task(
        dataset=load_dataset(dataset_path),
        # Classify-only: domain mode grades the classified domain and nothing
        # else, so generating a reply per sample is pure cost. See the solver's
        # docstring for the turn-1 equivalence that makes this faithful.
        solver=empathysync_classify_only(engine, ollama_host),
        scorer=domain_scorer(),
        # The scorer makes no model call and the solver drives the pipeline
        # directly; set to the (local, cheap) engine only so Inspect resolves a
        # model. It is never actually called.
        model=f"ollama/{engine}",
        fail_on_error=0.2,
    )


@task
def empathysync_bare(
    dataset_path: str = str(STARTER_DATASET),
    engine: str = DEFAULT_ENGINE,
    judge: str = DEFAULT_JUDGE,
    ollama_host: str = "",
    temperature: float = 0.0,
    grade: str = "restraint",
) -> Task:
    """Ablation arm: the same engine with no pipeline, graded by the same judge.

    Run this against `empathysync_restraint` on the same dataset and the
    difference is what the architecture contributes, as opposed to what the model
    was going to do anyway. Everything but the pipeline is held constant - engine,
    decoding, host, judge, rubric, corpus.

    The judge and rubric are deliberately unchanged. Grading this arm on a
    friendlier rubric would make the comparison meaningless.
    """
    return Task(
        dataset=load_dataset(dataset_path),
        solver=bare_engine(engine, ollama_host, temperature),
        scorer=_grader(grade, judge),
        model=f"ollama/{judge}",
        fail_on_error=0.2,
    )
