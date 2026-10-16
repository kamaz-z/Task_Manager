from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Task, TaskPriority, TaskStatus


def future(days: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


async def create(client, headers, **extra):
    return await client.post(
        "/tasks",
        json={"title": "Task", **extra},
        headers=headers,
    )


async def set_status(client, headers, task_id: int, new_status: str):
    return await client.patch(
        f"/tasks/{task_id}/status",
        json={"status": new_status},
        headers=headers,
    )


async def to_done(client, headers, task_id: int):
    for task_status in ("in_progress", "review", "done"):
        response = await set_status(client, headers, task_id, task_status)
        assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_deadline_in_past_rejected(client, make_user):
    _, headers = await make_user("a@test.com")
    response = await create(client, headers, deadline=future(-1))
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_valid_transition_and_back_is_forbidden(client, make_user):
    _, headers = await make_user("a@test.com")
    response = await create(client, headers)
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]

    assert (await set_status(client, headers, task_id, "in_progress")).status_code == 200
    assert (await set_status(client, headers, task_id, "review")).status_code == 200
    assert (await set_status(client, headers, task_id, "in_progress")).status_code == 409
    assert (await set_status(client, headers, task_id, "done")).status_code == 409


@pytest.mark.asyncio
async def test_done_requires_assignee(client, make_user):
    _, headers = await make_user("a@test.com")
    task_id = (await create(client, headers)).json()["id"]
    await set_status(client, headers, task_id, "in_progress")
    await set_status(client, headers, task_id, "review")

    response = await set_status(client, headers, task_id, "done")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_done_with_expired_deadline_rejected(client, make_user, session_maker):
    _, headers = await make_user("a@test.com")
    response = await create(
        client,
        headers,
        assignee_id=(await make_user("b@test.com"))[0],
        deadline=future(1),
    )
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    await set_status(client, headers, task_id, "in_progress")
    await set_status(client, headers, task_id, "review")

    async with session_maker() as db:
        task = await db.get(Task, task_id)
        task.deadline = datetime.now(timezone.utc) - timedelta(days=1)
        await db.commit()

    response = await set_status(client, headers, task_id, "done")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_done_task_cannot_be_edited(client, make_user):
    user_id, headers = await make_user("a@test.com")
    response = await create(client, headers, assignee_id=user_id)
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    await to_done(client, headers, task_id)

    response = await client.patch(
        f"/tasks/{task_id}",
        json={"title": "New"},
        headers=headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_cannot_change_assignee_in_review(client, make_user):
    user_id, headers = await make_user("a@test.com")
    other_id, _ = await make_user("b@test.com")
    response = await create(client, headers, assignee_id=user_id)
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    await set_status(client, headers, task_id, "in_progress")
    await set_status(client, headers, task_id, "review")

    response = await client.patch(
        f"/tasks/{task_id}",
        json={"assignee_id": other_id},
        headers=headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_cannot_delete_in_progress(client, make_user):
    _, headers = await make_user("a@test.com")
    task_id = (await create(client, headers)).json()["id"]
    await set_status(client, headers, task_id, "in_progress")

    assert (await client.delete(f"/tasks/{task_id}", headers=headers)).status_code == 409
    assert (await set_status(client, headers, task_id, "cancelled")).status_code == 200
    assert (await client.delete(f"/tasks/{task_id}", headers=headers)).status_code == 204


@pytest.mark.asyncio
async def test_active_tasks_limit(client, make_user):
    user_id, headers = await make_user("a@test.com")
    for _ in range(10):
        response = await create(client, headers, assignee_id=user_id)
        assert response.status_code == 201, response.text

    response = await create(client, headers, assignee_id=user_id)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_only_author_or_assignee_changes_status(client, make_user):
    _, headers = await make_user("a@test.com")
    _, stranger_headers = await make_user("b@test.com")
    task_id = (await create(client, headers)).json()["id"]

    response = await set_status(client, stranger_headers, task_id, "in_progress")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_default_sorting_priority_then_deadline(client, make_user):
    _, headers = await make_user("a@test.com")
    tasks = (
        ("low", "low", 1),
        ("high-late", "high", 5),
        ("high-soon", "high", 2),
    )
    for title, priority, days in tasks:
        response = await create(
            client,
            headers,
            title=title,
            priority=priority,
            deadline=future(days),
        )
        assert response.status_code == 201, response.text

    response = await client.get("/tasks", headers=headers)
    assert response.status_code == 200, response.text
    assert [task["title"] for task in response.json()["items"]] == [
        "high-soon",
        "high-late",
        "low",
    ]
