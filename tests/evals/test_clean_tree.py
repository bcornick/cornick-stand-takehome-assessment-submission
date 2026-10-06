# ABOUTME: Tests the clean-tree check of `make eval` on a real temporary git repository: it passes a committed tree, refuses a changed or untracked file, and ignores the results log.
# ABOUTME: The check runs in process against the repository it is given.
import subprocess
from pathlib import Path

import pytest

from evals.clean_tree import main


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q")
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "results.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "code.py").write_text("x = 1\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "start")
    return tmp_path


def test_a_committed_tree_passes_even_with_the_results_log_changed(repo: Path) -> None:
    (repo / "evals" / "results.jsonl").write_text("{}\n{}\n", encoding="utf-8")

    assert main(repo) == 0


def test_a_changed_file_is_refused_with_a_message_naming_it(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "code.py").write_text("x = 2\n", encoding="utf-8")

    assert main(repo) == 1
    assert "code.py" in capsys.readouterr().err


def test_an_untracked_file_is_refused(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "new.py").write_text("y = 1\n", encoding="utf-8")

    assert main(repo) == 1
    assert "new.py" in capsys.readouterr().err
