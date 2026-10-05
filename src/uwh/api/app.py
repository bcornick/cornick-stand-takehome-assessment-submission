# ABOUTME: The app factory: its lifespan opens the runtime, recovers an interrupted run before serving, and serves the routes of run.py, commands.py, replies.py and routes.py and the built frontend.
# ABOUTME: The factory reads settings when called, never at import, and opens no database and no service client until the app starts.
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from uwh.api import commands, replies, run
from uwh.api.routes import router
from uwh.api.runtime import open_runtime
from uwh.runtime.leadgen_client import LeadgenClient
from uwh.runtime.mailbox_client import MailboxClient
from uwh.runtime.runs import resume_after_restart
from uwh.settings import Settings


def create_app(
    settings: Settings | None = None,
    *,
    leadgen: LeadgenClient | None = None,
    mailbox: MailboxClient | None = None,
) -> FastAPI:
    """Build the app. At startup a service client that is not passed is built from the settings' URL for
    that service; a test passes clients that reach Stand's apps in process. The lifespan runs the
    restart recovery of 7.1 and 7.5 before the app serves."""
    settings = Settings.load() if settings is None else settings

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with open_runtime(settings, leadgen, mailbox) as runtime:
            resume_after_restart(settings.db_path, runtime.env)
            app.state.runtime = runtime
            yield

    app = FastAPI(title="Underwriting triage", version="1", lifespan=lifespan)
    app.include_router(run.router)
    app.include_router(commands.router)
    app.include_router(replies.router)
    app.include_router(router)
    # Mounted last so the API routes match first; absent in a checkout without a build.
    if Path(settings.static_dir).is_dir():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
    return app
