from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskPriority, TaskStatus, User
from app.schemas.task import TaskCreate, TaskUpdate

# Звідки куди можна перейти. Чого тут немає, те заборонено (зокрема "назад").
ALLOWED_TRANSITIONS = {
    TaskStatus.BACKLOG: [TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED],
    TaskStatus.IN_PROGRESS: [TaskStatus.REVIEW, TaskStatus.CANCELLED],
    TaskStatus.REVIEW: [TaskStatus.DONE],
    TaskStatus.DONE: [],
    TaskStatus.CANCELLED: [],
}

ACTIVE_STATUSES = [TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]
FINAL_STATUSES = [TaskStatus.DONE, TaskStatus.CANCELLED]
MAX_ACTIVE_TASKS = 10


# ---------- допоміжні перевірки ----------

def _normalize_deadline(deadline: datetime | None) -> datetime | None:
    """Приводить дату до UTC. Якщо зони немає, вважаємо, що це UTC."""
    if deadline is None:
        return None
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return deadline.astimezone(timezone.utc)


def _check_deadline(deadline: datetime | None) -> None:
    if deadline is not None and deadline < datetime.now(timezone.utc):
        raise HTTPException(422, "Дедлайн не може бути в минулому")


async def _check_assignee_exists(db: AsyncSession, assignee_id: int | None) -> None:
    if assignee_id is not None and await db.get(User, assignee_id) is None:
        raise HTTPException(404, "Виконавця не знайдено")


async def _check_assignee_limit(db: AsyncSession, assignee_id: int | None) -> None:
    """Не більше 10 активних задач на одного виконавця."""
    if assignee_id is None:
        return
    count = await db.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.assignee_id == assignee_id, Task.status.in_(ACTIVE_STATUSES))
    )
    if count >= MAX_ACTIVE_TASKS:
        raise HTTPException(
            409, f"Виконавець уже має {MAX_ACTIVE_TASKS} активних задач"
        )


def _check_is_author(task: Task, user: User) -> None:
    if task.author_id != user.id:
        raise HTTPException(403, "Лише автор може змінювати або видаляти задачу")


# ---------- CRUD ----------

async def get_task(db: AsyncSession, task_id: int) -> Task:
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Задачу не знайдено")
    return task


async def create_task(db: AsyncSession, data: TaskCreate, author: User) -> Task:
    deadline = _normalize_deadline(data.deadline)
    _check_deadline(deadline)
    await _check_assignee_exists(db, data.assignee_id)
    await _check_assignee_limit(db, data.assignee_id)

    task = Task(
        title=data.title,
        description=data.description,
        priority=data.priority,
        deadline=deadline,
        assignee_id=data.assignee_id,
        author_id=author.id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def update_task(
    db: AsyncSession, task_id: int, data: TaskUpdate, user: User
) -> Task:
    task = await get_task(db, task_id)
    _check_is_author(task, user)

    # Done і Cancelled редагувати не можна
    if task.status in FINAL_STATUSES:
        raise HTTPException(409, f"Задачу в статусі {task.status.value} не можна редагувати")

    fields = data.model_dump(exclude_unset=True)

    for name in ("title", "priority"):
        if name in fields and fields[name] is None:
            raise HTTPException(422, f"Поле {name} не може бути null")

    if "deadline" in fields:
        fields["deadline"] = _normalize_deadline(fields["deadline"])
        _check_deadline(fields["deadline"])

    # Перевіряємо виконавця, лише якщо його справді міняють на іншого
    if "assignee_id" in fields and fields["assignee_id"] != task.assignee_id:
        if task.status == TaskStatus.REVIEW:
            raise HTTPException(409, "Не можна змінювати виконавця в статусі Review")
        await _check_assignee_exists(db, fields["assignee_id"])
        await _check_assignee_limit(db, fields["assignee_id"])

    for name, value in fields.items():
        setattr(task, name, value)

    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task_id: int, user: User) -> None:
    task = await get_task(db, task_id)
    _check_is_author(task, user)

    if task.status in (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW):
        raise HTTPException(
            409, "Спочатку переведіть задачу в Cancelled або завершіть (Done)"
        )

    await db.delete(task)
    await db.commit()


# ---------- зміна статусу ----------

async def change_status(
    db: AsyncSession, task_id: int, new_status: TaskStatus, user: User
) -> Task:
    task = await get_task(db, task_id)

    if user.id not in (task.author_id, task.assignee_id):
        raise HTTPException(403, "Статус може змінювати лише автор або виконавець")

    if new_status not in ALLOWED_TRANSITIONS[task.status]:
        raise HTTPException(
            409,
            f"Перехід {task.status.value} -> {new_status.value} заборонений",
        )

    if new_status == TaskStatus.DONE:
        if task.assignee_id is None:
            raise HTTPException(409, "Не можна завершити задачу без виконавця")
        if task.deadline is not None and task.deadline < datetime.now(timezone.utc):
            raise HTTPException(409, "Не можна завершити задачу: дедлайн минув")

    task.status = new_status
    await db.commit()
    await db.refresh(task)
    return task



async def list_tasks(
    db: AsyncSession,
    q: str | None,
    status_filter: TaskStatus | None,
    priority: TaskPriority | None,
    assignee_id: int | None,
    deadline_before: datetime | None,
    deadline_after: datetime | None,
    sort_by: str | None,
    order: str,
    limit: int,
    offset: int,
) -> dict:

    
    filters = []
    if q:
        pattern = f"%{q}%"
        filters.append(or_(Task.title.ilike(pattern), Task.description.ilike(pattern)))
    if status_filter:
        filters.append(Task.status == status_filter)
    if priority:
        filters.append(Task.priority == priority)
    if assignee_id:
        filters.append(Task.assignee_id == assignee_id)
    if deadline_before:
        filters.append(Task.deadline <= _normalize_deadline(deadline_before))
    if deadline_after:
        filters.append(Task.deadline >= _normalize_deadline(deadline_after))

    priority_rank = case(
        (Task.priority == TaskPriority.HIGH, 1),
        (Task.priority == TaskPriority.MEDIUM, 2),
        (Task.priority == TaskPriority.LOW, 3),
    )

    if sort_by is None:
        order_by = [priority_rank, Task.deadline.asc().nulls_last(), Task.id]
    else:
        column = {
            "created_at": Task.created_at,
            "deadline": Task.deadline,
            "priority": priority_rank,
        }[sort_by]
        column = column.asc() if order == "asc" else column.desc()
        if sort_by == "deadline":
            column = column.nulls_last()
        order_by = [column, Task.id]

    total = await db.scalar(select(func.count()).select_from(Task).where(*filters))
    result = await db.scalars(
        select(Task).where(*filters).order_by(*order_by).limit(limit).offset(offset)
    )

    return {"items": result.all(), "total": total, "limit": limit, "offset": offset}



# прострочені і статистика

async def get_overdue_tasks(db: AsyncSession) -> list[Task]:
    result = await db.scalars(
        select(Task)
        .where(
            Task.deadline < datetime.now(timezone.utc),
            Task.status.not_in(FINAL_STATUSES),
        )
        .order_by(Task.deadline)
    )
    return list(result.all())


async def get_stats(db: AsyncSession) -> dict:
    total = await db.scalar(select(func.count()).select_from(Task))

    # Одразу всі статуси і пріоsритети з нулями, щоб відповідь була повною
    by_status = {s.value: 0 for s in TaskStatus}
    rows = await db.execute(select(Task.status, func.count()).group_by(Task.status))
    for task_status, count in rows:
        by_status[task_status.value] = count

    by_priority = {p.value: 0 for p in TaskPriority}
    rows = await db.execute(select(Task.priority, func.count()).group_by(Task.priority))
    for task_priority, count in rows:
        by_priority[task_priority.value] = count

    overdue = await db.scalar(
        select(func.count())
        .select_from(Task)
        .where(
            Task.deadline < datetime.now(timezone.utc),
            Task.status.not_in(FINAL_STATUSES),
        )
    )

    active = sum(by_status[s.value] for s in ACTIVE_STATUSES)

    return {
        "total": total,
        "by_status": by_status,
        "by_priority": by_priority,
        "overdue": overdue,
        "active": active,
    }