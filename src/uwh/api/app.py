# ABOUTME: The app's HTTP surface. The factory reads settings when called, never at import.
# ABOUTME: GET /api/run reports the run's mode, seed, id (null before a run starts) and summary; the other routes are declared in routes.py.
from fastapi import FastAPI

from uwh.api.routes import router
from uwh.api.views import RunSummary, RunView
from uwh.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = Settings.load() if settings is None else settings
    app = FastAPI(title="Underwriting triage", version="1")

    @app.get("/api/run")
    def get_run() -> RunView:
        return RunView(
            run_id=None,
            mode=settings.run_mode,
            seed=settings.seed,
            sim_now=None,
            first_pass_complete=False,
            summary=RunSummary(
                quotes_sent=0,
                follow_ups_sent=0,
                declines_approved=0,
                waiting_on_underwriter=0,
                waiting_on_data=0,
                delivery_unknown=0,
            ),
        )

    app.include_router(router)
    return app
