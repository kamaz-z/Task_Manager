from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.models import TaskPriority, TaskStatus
from app.schemas.task import (
    StatsRead,
    TaskCreate,
    TaskListResponse,
    TaskRead,
    TaskStatusChange,
    TaskUpdate,
)
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(data: TaskCreate, db: DbSession, user: CurrentUser):
    return await task_service.create_task(db, data, user)


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    db: DbSession,
    user: CurrentUser,
    q: str | None = None,
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = None,
    assignee_id: int | None = None,
    deadline_before: datetime | None = None,
    deadline_after: datetime | None = None,
    sort_by: Literal["created_at", "deadline", "priority"] | None = None,
    order: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await task_service.list_tasks(
        db, q, status_filter, priority, assignee_id,
        deadline_before, deadline_after, sort_by, order, limit, offset,
    )


@router.get("/overdue", response_model=list[TaskRead])
async def overdue_tasks(db: DbSession, user: CurrentUser):
    return await task_service.get_overdue_tasks(db)


@router.get("/stats", response_model=StatsRead)
async def stats(db: DbSession, user: CurrentUser):
    return await task_service.get_stats(db)


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, db: DbSession, user: CurrentUser):
    return await task_service.get_task(db, task_id)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int, data: TaskUpdate, db: DbSession, user: CurrentUser
):
    return await task_service.update_task(db, task_id, data, user)


@router.patch("/{task_id}/status", response_model=TaskRead)
async def change_status(
    task_id: int, data: TaskStatusChange, db: DbSession, user: CurrentUser
):
    return await task_service.change_status(db, task_id, data.status, user)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, db: DbSession, user: CurrentUser):
    await task_service.delete_task(db, task_id, user)