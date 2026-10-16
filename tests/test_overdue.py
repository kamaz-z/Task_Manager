from datetime import datetime, timedelta, timezone

import pytest
from app.models import Task, TaskPriority, TaskStatus
from app.services.overdue_service import cancel_overdue_tasks


async def make_past(session_maker, task_id: int):
    async with session_maker() as db:
        task = await db.get(Task, task_id)
        task.deadline = datetime.now(timezone.utc) - timedelta(days=1)
        await db.commit()


@pytest.mark.asyncio
async def test_overdue_task_is_cancelled(client, make_user, session_maker):
    _, headers = await make_user("a@test.com")
    response = await client.post("/tasks", json={"title": "T"}, headers=headers)
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    await make_past(session_maker, task_id)

    response = await client.get("/tasks/overdue", headers=headers)
    assert [task["id"] for task in response.json()] == [task_id]

    assert await cancel_overdue_tasks(session_maker) == 1

    response = await client.get(f"/tasks/{task_id}", headers=headers)
    assert response.json()["status"] == TaskStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_done_task_is_not_cancelled(client, make_user, session_maker):
    user_id, headers = await make_user("a@test.com")
    response = await client.post(
        "/tasks",
        json={"title": "T", "assignee_id": user_id, "deadline": (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat()},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]

    for task_status in ("in_progress", "review", "done"):
        response = await client.patch(
            f"/tasks/{task_id}/status",
            json={"status": task_status},
            headers=headers,
        )
        assert response.status_code == 200, response.text
    await make_past(session_maker, task_id)

    assert await cancel_overdue_tasks(session_maker) == 0

    response = await client.get(f"/tasks/{task_id}", headers=headers)
    assert response.json()["status"] == TaskStatus.DONE.value


@pytest.mark.asyncio
async def test_stats(client, make_user):
    _, headers = await make_user("a@test.com")
    response = await client.post(
        "/tasks",
        json={"title": "T", "priority": TaskPriority.HIGH.value},
        headers=headers,
    )
    assert response.status_code == 201, response.text

    response = await client.get("/tasks/stats", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 1
    assert data["by_status"][TaskStatus.BACKLOG.value] == 1
    assert data["by_status"][TaskStatus.DONE.value] == 0
    assert data["by_priority"][TaskPriority.HIGH.value] == 1
    assert data["active"] == 1
    assert data["overdue"] == 0
