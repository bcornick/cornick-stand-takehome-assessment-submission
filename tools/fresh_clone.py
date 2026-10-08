# ABOUTME: The fresh-clone rehearsal (14): clones HEAD into a temporary directory, copies .env.example to .env with no keys, brings the stack up in replay mode under its own compose project and host ports, runs the demo's first pass, asks the example prompts and delivers the fixture replies, then removes the stack and the clone.
# ABOUTME: Prints one line per step and exits 0; a failing step prints its output and exits 1. Only committed files are cloned, so commit before rehearsing.
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import httpx2

ROOT = Path(__file__).resolve().parents[1]
FIRST_PASS_LEADS = 10
HEALTH_TIMEOUT_SECONDS = 120
START_TIMEOUT_SECONDS = 300
# Variables the rehearsal must not inherit: it runs with no keys, in replay.
KEY_VARIABLES = ("MODEL_API_KEY", "TYPESAFE_API_KEY", "RUN_MODE", "RECORDINGS_ACCESS")


class StepFailed(Exception):
    """A step did not hold; the message is its output."""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    """The command's output; raises StepFailed with that output when it exits non-zero."""
    done = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    output = done.stdout + done.stderr
    if done.returncode != 0:
        raise StepFailed(f"{' '.join(command)} exited {done.returncode}\n{output}")
    return output


def step(name: str, action: Callable[[], str]) -> None:
    """Run `action`, then print `name` with the one-line result it returns."""
    print(f"... {name}", flush=True)
    result = action()
    print(f"ok  {name}: {result}", flush=True)


def wait_for_health(app_url: str) -> str:
    deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            if httpx2.get(f"{app_url}/api/run", timeout=3).status_code == 200:
                return f"{app_url}/api/run answers"
        except httpx2.HTTPError:
            pass
        time.sleep(2)
    raise StepFailed(f"{app_url}/api/run did not answer within {HEALTH_TIMEOUT_SECONDS} seconds")


def first_pass(app_url: str) -> str:
    response = httpx2.post(f"{app_url}/api/run/start?wait=true", timeout=START_TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise StepFailed(f"start answered {response.status_code}: {response.text}")
    run_view = response.json()
    leads = httpx2.get(f"{app_url}/api/leads", timeout=10).json()
    if run_view["mode"] != "replay":
        raise StepFailed(f"the app runs in {run_view['mode']} mode, not replay")
    if len(leads) != FIRST_PASS_LEADS or not run_view["first_pass_complete"]:
        raise StepFailed(
            f"expected {FIRST_PASS_LEADS} leads and a complete first pass; "
            f"got {len(leads)} leads, first_pass_complete={run_view['first_pass_complete']}"
        )
    return f"{len(leads)} leads, first pass complete, mode replay"


def example_prompts(app_url: str) -> str:
    """Ask each example prompt first in the queue conversation; replay answers it from its recording."""
    prompts = httpx2.get(f"{app_url}/api/run", timeout=10).json()["example_prompts"]
    for prompt in prompts:
        stream = httpx2.post(f"{app_url}/api/chat", json={"message": prompt}, timeout=60).text
        events = [
            json.loads(line.removeprefix("data: "))
            for line in stream.splitlines()
            if line.startswith("data: ")
        ]
        closing = events[-1] if events else {}
        if closing.get("type") != "answer" or not closing["citations"]:
            raise StepFailed(f"{prompt!r} did not close with a cited answer: {closing}")
    return f"{len(prompts)} example prompts answered from recordings, each with citations"


def fixture_replies(app_url: str, clone: Path) -> str:
    response = httpx2.post(f"{app_url}/api/replies/fixtures", timeout=START_TIMEOUT_SECONDS)
    delivered = response.json()["replies"]
    # A lead whose request is held for the underwriter's choice has nothing out to answer, so its
    # fixture is skipped; every reply that is delivered must be accepted.
    stored = len(list((clone / "fixtures" / "replies").glob("*.txt")))
    refused = [r for r in delivered if not r["accepted"]]
    if refused or not delivered:
        raise StepFailed(f"expected every delivered reply accepted; got {delivered}")
    return f"{len(delivered)} of {stored} fixture replies delivered and accepted; the rest wait on held requests"


def rehearse(workdir: Path, project: str) -> None:
    clone = workdir / "clone"
    ports = {"LEADGEN_PORT": free_port(), "MAILBOX_PORT": free_port(), "APP_PORT": free_port()}
    app_url = f"http://localhost:{ports['APP_PORT']}"
    commit = run(["git", "rev-parse", "HEAD"], ROOT).strip()
    env = {k: v for k, v in os.environ.items() if k not in KEY_VARIABLES}
    env.update({name: str(port) for name, port in ports.items()}, GIT_COMMIT=commit)
    compose = ["docker", "compose", "-p", project]

    def clone_head() -> str:
        run(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(clone)], workdir)
        return f"{commit[:12]} cloned"

    def copy_env() -> str:
        shutil.copyfile(clone / ".env.example", clone / ".env")
        return ".env copied from .env.example, no keys"

    def bring_up() -> str:
        run([*compose, "up", "--build", "--detach", "--wait"], clone, env)
        return f"project {project}, host ports {sorted(ports.values())}"

    step("clone HEAD", clone_head)
    step("cp .env.example .env", copy_env)
    try:
        step("docker compose up --build", bring_up)
        step("health", lambda: wait_for_health(app_url))
        step("run start", lambda: first_pass(app_url))
        step("example prompts", lambda: example_prompts(app_url))
        step("fixture replies", lambda: fixture_replies(app_url, clone))
    finally:
        # Runs whether the steps held or not, so no container, volume or image is left behind.
        teardown(clone, project, env)
        print("ok  teardown: containers, volumes and images removed", flush=True)


def teardown(clone: Path, project: str, env: dict[str, str]) -> None:
    """Stop the project's containers and remove its volumes and the images it built."""
    run(["docker", "compose", "-p", project, "down", "--volumes", "--rmi", "local"], clone, env)


def main() -> int:
    project = f"uwh-fresh-clone-{os.getpid()}"
    workdir = Path(tempfile.mkdtemp(prefix="uwh-fresh-clone-"))
    try:
        rehearse(workdir, project)
    except StepFailed as failure:
        print(f"FAILED\n{failure}", file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    print("fresh-clone rehearsal passed; the stack and the clone are removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
