# ABOUTME: The check `make eval` runs on the host before the eval image is built: a run is recorded against a commit, so the working tree must match that commit.
# ABOUTME: Changes to the results log itself are ignored, since each run appends to it.
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = "evals/results.jsonl"


def uncommitted_changes(root: Path) -> list[str]:
    """The `git status --porcelain` lines of the repository at `root`, without the results log."""
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", ".", f":!{RESULTS}"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return status.stdout.splitlines()


def main(root: Path = ROOT) -> int:
    changes = uncommitted_changes(root)
    if changes:
        print(
            "make eval: the working tree has uncommitted changes, so the row's commit would not "
            "name the code that runs. Commit them first:",
            file=sys.stderr,
        )
        print("\n".join(changes), file=sys.stderr)
    return 1 if changes else 0


if __name__ == "__main__":
    sys.exit(main())
