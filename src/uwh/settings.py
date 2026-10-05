# ABOUTME: Runtime settings read from the environment when asked for, not at import.
# ABOUTME: Defaults are the in-network values; UWH_DB has no default and must be set.
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

RUN_MODES = ("live", "replay", "record")


@dataclass(frozen=True)
class Settings:
    run_mode: str
    seed: int
    model_id: str
    model_base_url: str
    leadgen_url: str
    mailbox_url: str
    registry_path: str
    db_path: str
    git_commit: str

    @classmethod
    def load(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        run_mode = env.get("RUN_MODE", "live")
        if run_mode not in RUN_MODES:
            raise ValueError(f"RUN_MODE must be one of {', '.join(RUN_MODES)}; got {run_mode!r}")
        try:
            seed = int(env.get("SEED", "42"))
        except ValueError:
            raise ValueError(f"SEED must be an integer; got {env['SEED']!r}") from None
        if "UWH_DB" not in env:
            raise ValueError("UWH_DB must be set to the path of the application database")
        return cls(
            run_mode=run_mode,
            seed=seed,
            model_id=env.get("MODEL_ID", "deepseek-flash"),
            model_base_url=env.get("MODEL_BASE_URL", "https://api.deepseek.com/anthropic"),
            leadgen_url=env.get("LEADGEN_URL", "http://leadgen:8080"),
            mailbox_url=env.get("MAILBOX_URL", "http://mailbox:8080"),
            registry_path=env.get("UWH_REGISTRY", "/app/registry/field_registry.json"),
            db_path=env["UWH_DB"],
            git_commit=env.get("GIT_COMMIT", "unknown"),
        )
