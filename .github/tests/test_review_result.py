"""The wrapper forwards the shared aggregate's structured outcome unchanged."""

from pathlib import Path

import yaml


def test_shared_review_result_reaches_the_wrapper_caller() -> None:
    path = Path(__file__).resolve().parents[1] / "workflows/wrapper.yml"
    workflow = yaml.safe_load(path.read_text())
    events = workflow.get("on", workflow.get(True))
    assert events["workflow_call"]["outputs"]["review_result"]["value"] == (
        "${{ jobs.review.outputs.review_result }}"
    )
    job = workflow["jobs"]["review"]
    assert (
        job["outputs"]["review_result"]
        == "${{ steps.aggregate.outputs.review_result }}"
    )
    aggregate = next(step for step in job["steps"] if step.get("id") == "aggregate")
    assert "aggregate_reviews.py" in aggregate["run"]
