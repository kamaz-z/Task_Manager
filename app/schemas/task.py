from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.models import TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    deadline: datetime | None = None
    assignee_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    priority: TaskPriority | None = None
    deadline: datetime | None = None
    assignee_id: int | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    deadline: datetime | None
    author_id: int
    assignee_id: int | None
    created_at: datetime
    updated_at: datetime

class TaskStatusChange(BaseModel):
    status: TaskStatus    

class TaskListResponse(BaseModel):
    items: list[TaskRead]
    total: int
    limit: int
    offset: int

class StatsRead(BaseModel):
    total: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    overdue: int
    active: int        