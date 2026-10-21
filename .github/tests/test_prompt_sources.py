"""Where 'Extract diff and context' takes the review prompts from (AT-2520).

The step body is extracted from wrapper.yml and run as the shell script it
is, against real local git repositories, and the context.md it writes is
read back. Its run body has no `${{ }}` expressions, so the env block is the
whole interface.

The order is: the consumer's base branch (a PR cannot rewrite its own review
instructions), then the PR head (first-time onboarding), then the wrapper's
canonical default checked out at `.wrapper-defaults`. Only ABSENCE falls
through. A prompt that is present but empty, or is not a regular file, fails
the step. Every source is read from git objects as a regular file (mode
100644 / 100755), so a symlink can never turn a prompt path into a read of a
runner-local file. This is the rule base ignite-corp/ai-dev-pr-review #210
set in base-ai-review-prepare.yml.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "wrapper.yml"

SYSTEM = ".github/prompts/code-review-system.md"
CHECKLIST = ".github/prompts/code-review-checklist.md"
DEFAULT_FILES = {
    ".prompts/code-review-system.md": "WRAPPER DEFAULT SYSTEM\n",
    ".prompts/code-review-checklist.md": "WRAPPER DEFAULT CHECKLIST\n",
}

_GIT_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=_GIT_ENV,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _commit(
    root: Path, message: str, files: dict[str, str], links: dict[str, Path]
) -> str:
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    for name, target in links.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _step_body() -> str:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["review"]["steps"]
    step = next(s for s in steps if s.get("name") == "Extract diff and context")
    assert "${{" not in step["run"]
    return step["run"]


def _make_repo(
    tmp_path: Path,
    *,
    base_files: dict[str, str],
    head_files: dict[str, str],
    base_links: dict[str, Path] | None = None,
    head_links: dict[str, Path] | None = None,
    default_files: dict[str, str] | None = None,
    default_links: dict[str, Path] | None = None,
) -> tuple[Path, str]:
    """`origin/main` carrying base_files, a work tree one commit ahead.

    The `*_links` maps commit a symlink at each path. `.wrapper-defaults` is
    built as a git repository, as the sparse actions/checkout leaves it.
    """
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))

    seed = tmp_path / "seed"
    _git(tmp_path, "init", "-q", "-b", "main", str(seed))
    _commit(seed, "base", {"README.md": "base\n", **base_files}, base_links or {})
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "main")

    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    _git(work, "checkout", "-q", "-b", "main", "origin/main")
    head_sha = _commit(
        work, "pr change", {"changed.txt": "hi\n", **head_files}, head_links or {}
    )

    # The metadata block imports display_path from the upstream checkout;
    # the identity is enough here, the prompt part is what is under test.
    scripts = work / ".ai-dev-pr-review" / ".github" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "github_pr_support.py").write_text(
        "def display_path(value):\n    return value\n", encoding="utf-8"
    )

    defaults = work / ".wrapper-defaults"
    _git(work, "init", "-q", "-b", "main", str(defaults))
    _commit(
        defaults,
        "defaults",
        DEFAULT_FILES if default_files is None else default_files,
        default_links or {},
    )
    return work, head_sha


def _run(work: Path, head_sha: str) -> subprocess.CompletedProcess[str]:
    runner_temp = work.parent / "runner-temp"
    runner_temp.mkdir(exist_ok=True)
    env = {
        **_GIT_ENV,
        "RUNNER_TEMP": str(runner_temp),
        "GH_TOKEN": "gh-token",
        "PR_NUMBER": "7",
        "GITHUB_REPOSITORY": "ignite-pilot-org/consumer",
        "BASE_REF": "main",
        "HEAD_SHA": head_sha,
        "PR_AUTHOR": "someuser",
        "HEAD_REF": "task/x",
        "PR_MERGED": "false",
        "MERGE_COMMIT_SHA": "",
        "PR_COMMITS": "1",
        "LABELS": "",
        "SYSTEM_PROMPT_PATH": SYSTEM,
        "CHECKLIST_PATH": CHECKLIST,
    }
    # `bash -e`: what the runner uses for a `run:` with no `shell:` set.
    return subprocess.run(
        ["bash", "-e", "-c", _step_body()],
        env=env,
        cwd=work,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _context(work: Path) -> str:
    path = work / "context.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _planted(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("PLANTED-SECRET\n", encoding="utf-8")
    return secret


class TestPrecedence:
    def test_base_branch_copy_wins_over_the_head(self, tmp_path: Path) -> None:
        work, head = _make_repo(
            tmp_path,
            base_files={SYSTEM: "BASE SYSTEM\n", CHECKLIST: "BASE CHECKLIST\n"},
            head_files={SYSTEM: "HEAD SYSTEM\n", CHECKLIST: "HEAD CHECKLIST\n"},
        )
        result = _run(work, head)
        assert result.returncode == 0, result.stdout + result.stderr
        context_md = _context(work)
        assert "BASE SYSTEM\n\n\n---\n\nBASE CHECKLIST\n" in context_md
        assert "HEAD" not in context_md
        assert result.stdout.count("::notice title=Review prompt source") == 2

    def test_onboarding_head_copy_is_used_with_its_warning(
        self, tmp_path: Path
    ) -> None:
        work, head = _make_repo(
            tmp_path,
            base_files={},
            head_files={SYSTEM: "HEAD SYSTEM\n", CHECKLIST: "HEAD CHECKLIST\n"},
        )
        result = _run(work, head)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "HEAD SYSTEM\n\n\n---\n\nHEAD CHECKLIST\n" in _context(work)
        assert result.stdout.count("Onboarding prompt fallback") == 2


class TestMissingFallsBackToTheWrapperDefault:
    def test_missing_on_both_sides_reads_the_default(self, tmp_path: Path) -> None:
        work, head = _make_repo(tmp_path, base_files={}, head_files={})
        result = _run(work, head)
        assert result.returncode == 0, result.stdout + result.stderr
        assert (
            "WRAPPER DEFAULT SYSTEM\n\n\n---\n\nWRAPPER DEFAULT CHECKLIST\n"
            in _context(work)
        )
        warnings = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("::warning title=Using wrapper canonical default")
        ]
        assert len(warnings) == 2

    def test_one_missing_file_defaults_alone(self, tmp_path: Path) -> None:
        work, head = _make_repo(
            tmp_path, base_files={SYSTEM: "BASE SYSTEM\n"}, head_files={}
        )
        result = _run(work, head)
        assert result.returncode == 0, result.stdout + result.stderr
        context_md = _context(work)
        assert "BASE SYSTEM\n\n\n---\n\nWRAPPER DEFAULT CHECKLIST\n" in context_md
        assert "WRAPPER DEFAULT SYSTEM" not in context_md

    def test_default_missing_from_the_wrapper_checkout_fails(
        self, tmp_path: Path
    ) -> None:
        work, head = _make_repo(
            tmp_path,
            base_files={},
            head_files={},
            default_files={".prompts/code-review-system.md": "S\n"},
        )
        result = _run(work, head)
        assert result.returncode != 0
        assert "::error" in result.stdout and "code-review-checklist.md" in result.stdout

    @pytest.mark.parametrize("content", ["", "\n  \n"])
    def test_empty_default_fails(self, tmp_path: Path, content: str) -> None:
        work, head = _make_repo(
            tmp_path,
            base_files={},
            head_files={},
            default_files={
                ".prompts/code-review-system.md": content,
                ".prompts/code-review-checklist.md": "C\n",
            },
        )
        result = _run(work, head)
        assert result.returncode != 0
        assert "::error title=Empty review prompt" in result.stdout

    def test_symlinked_default_fails(self, tmp_path: Path) -> None:
        secret = _planted(tmp_path)
        work, head = _make_repo(
            tmp_path,
            base_files={},
            head_files={},
            default_files={".prompts/code-review-checklist.md": "C\n"},
            default_links={".prompts/code-review-system.md": secret},
        )
        result = _run(work, head)
        assert result.returncode != 0
        assert "::error" in result.stdout and "120000" in result.stdout
        context_md = _context(work)
        assert "PLANTED-SECRET" not in context_md
        assert str(secret) not in context_md


class TestPresentButBrokenFailsClosed:
    @pytest.mark.parametrize("content", ["", "\n  \n"])
    def test_empty_prompt_on_the_base_branch_fails(
        self, tmp_path: Path, content: str
    ) -> None:
        work, head = _make_repo(
            tmp_path, base_files={SYSTEM: content, CHECKLIST: "C\n"}, head_files={}
        )
        result = _run(work, head)
        assert result.returncode != 0
        assert "::error title=Empty review prompt" in result.stdout
        assert SYSTEM in result.stdout
        assert "WRAPPER DEFAULT" not in _context(work)

    @pytest.mark.parametrize("content", ["", "\n  \n"])
    def test_empty_prompt_on_the_head_fails(
        self, tmp_path: Path, content: str
    ) -> None:
        work, head = _make_repo(
            tmp_path, base_files={}, head_files={SYSTEM: "S\n", CHECKLIST: content}
        )
        result = _run(work, head)
        assert result.returncode != 0
        assert "::error title=Empty review prompt" in result.stdout
        assert CHECKLIST in result.stdout

    def test_directory_at_the_prompt_path_fails(self, tmp_path: Path) -> None:
        work, head = _make_repo(
            tmp_path,
            base_files={f"{SYSTEM}/nested.md": "x\n", CHECKLIST: "C\n"},
            head_files={},
        )
        result = _run(work, head)
        assert result.returncode != 0
        assert "::error" in result.stdout and "040000" in result.stdout


class TestSymlinkedPromptNeverReadsOutsideTheTree:
    """A prompt path must not become a way to read a runner-local file.

    git stores a symlink as a blob of mode 120000 whose content is the link
    target, so `git show` on the base branch prints the target path; and a
    `cat` of the PR head's working tree follows it to whatever it names.
    """

    def test_symlink_on_the_base_branch_fails(self, tmp_path: Path) -> None:
        secret = _planted(tmp_path)
        work, head = _make_repo(
            tmp_path,
            base_files={CHECKLIST: "C\n"},
            head_files={},
            base_links={SYSTEM: secret},
        )
        result = _run(work, head)
        assert result.returncode != 0
        assert "::error" in result.stdout and "120000" in result.stdout
        context_md = _context(work)
        assert str(secret) not in context_md
        assert "PLANTED-SECRET" not in context_md

    def test_symlink_on_the_head_fails(self, tmp_path: Path) -> None:
        secret = _planted(tmp_path)
        work, head = _make_repo(
            tmp_path,
            base_files={},
            head_files={CHECKLIST: "C\n"},
            head_links={SYSTEM: secret},
        )
        result = _run(work, head)
        assert result.returncode != 0
        assert "::error" in result.stdout and "120000" in result.stdout
        context_md = _context(work)
        assert "PLANTED-SECRET" not in context_md
        assert str(secret) not in context_md

    def test_symlinked_parent_directory_on_the_head_is_not_followed(
        self, tmp_path: Path
    ) -> None:
        # The link sits on a parent directory, so the prompt path itself is
        # not a link: in git objects the path does not exist below a blob,
        # so the prompt is absent and the wrapper default is read instead.
        outside = tmp_path / "outside-dir"
        outside.mkdir()
        for name in ("code-review-system.md", "code-review-checklist.md"):
            (outside / name).write_text("PLANTED-SECRET\n", encoding="utf-8")
        work, head = _make_repo(
            tmp_path,
            base_files={},
            head_files={},
            head_links={".github/prompts": outside},
        )
        result = _run(work, head)
        assert result.returncode == 0, result.stdout + result.stderr
        context_md = _context(work)
        assert "PLANTED-SECRET" not in context_md
        assert "WRAPPER DEFAULT SYSTEM" in context_md


def test_wrapper_defaults_checkout_is_pinned_to_the_paired_release() -> None:
    # The release PR moves the ref and the header's "Current pairing" line
    # together, to a tag that exists once that PR merges; a feature PR
    # moves neither, so the two must always name the same wrapper release.
    text = WORKFLOW.read_text(encoding="utf-8")
    pairing = re.search(r"Current pairing: wrapper\n# (v\d+\.\d+\.\d+) <-> base", text)
    assert pairing, "header no longer states the current wrapper pairing"
    workflow = yaml.safe_load(text)
    step = next(
        s
        for s in workflow["jobs"]["review"]["steps"]
        if s.get("name", "").startswith("Checkout wrapper canonical default prompts")
    )
    assert step["with"]["path"] == ".wrapper-defaults"
    assert step["with"]["ref"] == pairing.group(1)
