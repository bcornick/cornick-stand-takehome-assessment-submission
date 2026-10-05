# ABOUTME: Tests of tools/check_generated_types.py: it passes when web/src/api/types.ts is what the generator makes from openapi.json and fails when the file differs or is absent.
# ABOUTME: Each test works on a temporary copy of types.ts; the tracked file is only read, and the tool leaves no temporary file behind.
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check_generated_types.py"
TRACKED = ROOT / "web" / "src" / "api" / "types.ts"


def run_tool(types: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), "--types", str(types)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_tracked_types_are_what_the_generator_makes(tmp_path: Path) -> None:
    result = run_tool(TRACKED)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def test_a_hand_edited_types_file_fails_and_is_not_rewritten(tmp_path: Path) -> None:
    edited = tmp_path / "types.ts"
    edited.write_text(TRACKED.read_text(encoding="utf-8") + "export type Extra = string\n")
    before = edited.read_bytes()
    result = run_tool(edited)
    assert result.returncode == 1
    assert "differs" in result.stderr and "Extra" in result.stderr
    assert edited.read_bytes() == before


def test_an_absent_types_file_fails(tmp_path: Path) -> None:
    result = run_tool(tmp_path / "missing.ts")
    assert result.returncode == 1
    assert "missing" in result.stderr


def test_the_tool_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    temp_root = Path(tempfile.gettempdir())
    before = {p.name for p in temp_root.glob("check-types-*")}
    run_tool(TRACKED)
    run_tool(tmp_path / "missing.ts")
    assert {p.name for p in temp_root.glob("check-types-*")} == before
