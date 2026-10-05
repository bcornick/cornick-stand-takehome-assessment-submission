# ABOUTME: Writes the app's OpenAPI document to web/src/api/openapi.json in a fixed form; --check fails when the file is absent or differs.
# ABOUTME: It builds the app from explicit settings, so it needs no environment and opens no database.
import argparse
import json
import sys
from pathlib import Path

from uwh.api.app import create_app
from uwh.settings import Settings

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "web" / "src" / "api" / "openapi.json"


def render() -> bytes:
    """The document with sorted keys, two-space indent, a trailing newline and LF line ends."""
    document = create_app(Settings.load({"UWH_DB": "unused.db"})).openapi()
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail when the file differs; write nothing"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    document = render()
    if args.check:
        if not args.output.is_file():
            print(
                f"{args.output} is missing; run: uv run python tools/export_openapi.py",
                file=sys.stderr,
            )
            return 1
        if args.output.read_bytes() != document:
            print(
                f"{args.output} differs from the app's OpenAPI document; "
                "run: uv run python tools/export_openapi.py",
                file=sys.stderr,
            )
            return 1
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(document)
    return 0


if __name__ == "__main__":
    sys.exit(main())
