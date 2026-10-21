"""The wrapper's canonical default prompts state the reviewer JSON contract.

Every consumer without prompts of its own is reviewed against `.prompts/`
(checked out as `.wrapper-defaults`). The reviewers' output is parsed as the
JSON findings the review schema defines, so a default prompt that asks for a
markdown report contradicts the contract each reviewer step enforces. The
Output Format section is base's `examples/prompts/code-review-system.md`
(ignite-corp/ai-dev-pr-review v1.14.0).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROMPTS = Path(__file__).resolve().parents[2] / ".prompts"
SYSTEM = PROMPTS / "code-review-system.md"
DEFAULT_PROMPTS = sorted(PROMPTS.glob("*.md"))

# Headings of the markdown-report template the default used to request.
REPORT_TEMPLATE_MARKERS = ("## AI Code Review", "### Summary", "```markdown")


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match, f"no {heading!r} section"
    return match.group(1)


def test_default_prompts_are_present() -> None:
    assert [p.name for p in DEFAULT_PROMPTS] == [
        "code-review-checklist.md",
        "code-review-system.md",
    ]


def test_output_format_states_the_json_contract() -> None:
    section = _section(SYSTEM.read_text(encoding="utf-8"), "## Output Format")
    assert "Emit findings ONLY as the JSON" in section
    for field in ("`severity`", "`file`", "`line`", "`description`", "`suggestion`"):
        assert field in section
    assert "`.github/schemas/review-schema.json`" in section
    assert "Do not write a markdown report" in section
    assert "do not post PR\ncomments or reviews yourself" in section


@pytest.mark.parametrize("prompt", DEFAULT_PROMPTS, ids=lambda p: p.name)
def test_no_markdown_report_template(prompt: Path) -> None:
    text = prompt.read_text(encoding="utf-8")
    for marker in REPORT_TEMPLATE_MARKERS:
        assert marker not in text, f"{prompt.name} still carries {marker!r}"
