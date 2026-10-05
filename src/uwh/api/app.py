# ABOUTME: The app's HTTP surface. The factory reads settings when called, never at import.
# ABOUTME: GET /api/run reports the run mode, the seed and the run id (null before a run starts).
from fastapi import FastAPI

from uwh.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = Settings.load() if settings is None else settings
    app = FastAPI()

    @app.get("/api/run")
    def get_run() -> dict[str, str | int | None]:
        return {"mode": settings.run_mode, "seed": settings.seed, "run_id": None}

    return app
