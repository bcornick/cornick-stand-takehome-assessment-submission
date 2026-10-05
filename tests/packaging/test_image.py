# ABOUTME: Builds the app image from a temporary copy of the build inputs and checks the guarantees of architecture section 14.
# ABOUTME: Needs Docker only; a sentinel skill with a cases/ folder and an evals/ file exist in the copy, never in the repository.
import io
import subprocess
import tarfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parents[2]
KNOWN_COMMIT = "0123abc-image-test"
REGISTRY = "docs/brief/field_registry.json"


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[bytes]:
    """Run a command and fail with its full output when it exits non-zero."""
    result = subprocess.run(args, cwd=cwd, capture_output=True, check=False)
    assert result.returncode == 0, (
        f"{' '.join(args)} exited {result.returncode}\n"
        f"{result.stdout.decode(errors='replace')}\n{result.stderr.decode(errors='replace')}"
    )
    return result


@pytest.fixture(scope="module")
def context(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The build inputs copied into a temporary directory, plus the sentinel files."""
    ctx = tmp_path_factory.mktemp("image-context")
    for name in ("Dockerfile", ".dockerignore", "pyproject.toml", "uv.lock"):
        (ctx / name).write_bytes((ROOT / name).read_bytes())
    for source in (ROOT / "src").rglob("*"):
        if source.is_file() and "__pycache__" not in source.parts:
            target = ctx / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    (ctx / "docs/brief").mkdir(parents=True)
    (ctx / REGISTRY).write_bytes((ROOT / REGISTRY).read_bytes())
    for source in (ROOT / "web").rglob("*"):
        if source.is_file() and not {"node_modules", "dist"} & set(source.relative_to(ROOT).parts):
            target = ctx / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    sentinel = ctx / "src/uwh/skills/zz_sentinel"
    (sentinel / "cases").mkdir(parents=True)
    (sentinel / "cases/case.yaml").write_text("id: sentinel\n", encoding="utf-8")
    (sentinel / "keep.txt").write_text("kept\n", encoding="utf-8")
    (ctx / "evals").mkdir()
    (ctx / "evals/sentinel.txt").write_text("sentinel\n", encoding="utf-8")
    return ctx


def build(context: Path, tag: str, *build_args: str) -> None:
    run("docker", "build", "--target", "app", *build_args, "-t", tag, ".", cwd=context)


@pytest.fixture(scope="module")
def image(context: Path) -> Iterator[str]:
    tag = f"uwh-image-test:{uuid.uuid4().hex[:8]}"
    build(context, tag, "--build-arg", f"GIT_COMMIT={KNOWN_COMMIT}")
    yield tag
    subprocess.run(["docker", "image", "rm", "--force", tag], capture_output=True, check=False)


def in_image(image: str, *command: str) -> str:
    return run("docker", "run", "--rm", image, *command).stdout.decode()


def layer_member_names(image: str, tmp_path: Path) -> list[str]:
    """Every file name in every layer of the image, read from `docker save`."""
    archive = tmp_path / "image.tar"
    run("docker", "save", "-o", str(archive), image)
    names: list[str] = []
    with tarfile.open(archive) as outer:
        for member in outer:
            extracted = outer.extractfile(member) if member.isfile() else None
            if extracted is None:
                continue
            try:
                with tarfile.open(fileobj=io.BytesIO(extracted.read()), mode="r:*") as layer:
                    names.extend(layer.getnames())
            except tarfile.TarError:
                continue  # manifests, configs and indexes are not layers
    return names


def test_no_cases_folder_in_the_app_tree_and_the_rest_of_the_skill_stays(image: str) -> None:
    listing = in_image(image, "find", "/app", "-not", "-path", "/app/.venv/*").splitlines()
    assert "/app/src/uwh/skills/zz_sentinel/keep.txt" in listing
    assert [p for p in listing if p.rsplit("/", 1)[-1] == "cases"] == []
    assert [p for p in listing if p.endswith("case.yaml")] == []


def test_no_layer_of_the_image_holds_a_cases_folder(image: str, tmp_path: Path) -> None:
    names = layer_member_names(image, tmp_path)
    assert any(n.endswith("zz_sentinel/keep.txt") for n in names), "layer scan found no sentinel"
    offending = [n for n in names if "/cases/" in f"/{n}/" or n.endswith("case.yaml")]
    assert offending == []


def test_image_history_does_not_mention_the_case_file(image: str) -> None:
    # The history lists build instructions, not file names, so this catches only a
    # COPY or RUN that names the file; the layer scan above is the direct check.
    history = run("docker", "history", "--no-trunc", image).stdout.decode()
    assert "case.yaml" not in history


def test_no_evals_in_the_image(image: str) -> None:
    listing = in_image(image, "find", "/app", "-not", "-path", "/app/.venv/*").splitlines()
    assert [p for p in listing if p.rsplit("/", 1)[-1] in ("evals", "sentinel.txt")] == []


def test_image_holds_the_built_frontend_at_the_static_path(image: str) -> None:
    assert 'id="root"' in in_image(image, "cat", "/app/static/index.html")
    assets = in_image(image, "ls", "/app/static/assets").split()
    assert any(name.endswith(".js") for name in assets)
