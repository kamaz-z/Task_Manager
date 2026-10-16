import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers import auth, comments, tasks
from app.services.overdue_service import overdue_loop

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    background = asyncio.create_task(overdue_loop())
    yield

    background.cancel()
    try:
        await background
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Task Manager API", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(tasks.router)
app.include_router(comments.router)