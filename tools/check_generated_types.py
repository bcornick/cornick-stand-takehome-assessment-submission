# ABOUTME: Fails when web/src/api/types.ts differs from what openapi-typescript generates from web/src/api/openapi.json; writes nothing into the tree.
# ABOUTME: The generator runs offline into a temporary directory that is removed afterwards.
import argparse
import difflib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
OPENAPI = WEB / "src" / "api" / "openapi.json"
TYPES = WEB / "src" / "api" / "types.ts"
REGENERATE = "run: pnpm --dir web run gen:types"


def generate(openapi: Path, output: Path) -> None:
    subprocess.run(
        ["pnpm", "--dir", str(WEB), "exec", "openapi-typescript", str(openapi), "-o", str(output)],
        check=True,
        capture_output=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--types", type=Path, default=TYPES, help="the file to compare")
    args = parser.parse_args(argv)
    if not args.types.is_file():
        print(f"{args.types} is missing; {REGENERATE}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="check-types-") as directory:
        generated = Path(directory) / "types.ts"
        generate(OPENAPI, generated)
        expected = generated.read_text(encoding="utf-8").splitlines(keepends=True)
    actual = args.types.read_text(encoding="utf-8").splitlines(keepends=True)
    if expected == actual:
        return 0
    diff = difflib.unified_diff(actual, expected, str(args.types), "generated", n=1)
    print(
        f"{args.types} differs from the types generated from {OPENAPI}; {REGENERATE}",
        file=sys.stderr,
    )
    sys.stderr.writelines(list(diff)[:40])
    return 1


if __name__ == "__main__":
    sys.exit(main())
