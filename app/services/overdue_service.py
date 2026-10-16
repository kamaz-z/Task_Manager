import asyncio
import logging
from datetime import datetime, timezone
from sqlalchemy import update

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models import Task, TaskStatus

logger = logging.getLogger(__name__)


async def cancel_overdue_tasks(session_maker=AsyncSessionLocal) -> int:
    """Скасовує прострочені задачі. Повертає, скільки задач оновлено."""
    async with session_maker() as db:
        result = await db.execute(
            update(Task)
            .where(
                Task.deadline < datetime.now(timezone.utc),
                Task.status.not_in([TaskStatus.DONE, TaskStatus.CANCELLED]),
            )
            .values(status=TaskStatus.CANCELLED)
        )
        await db.commit()
        return result.rowcount


async def overdue_loop() -> None:
    while True:
        try:
            count = await cancel_overdue_tasks()
            if count:
                logger.info("Скасовано прострочених задач: %s", count)
        except Exception:
            # помилка не повинна зупиняти цикл
            logger.exception("Помилка при перевірці прострочених задач")
        await asyncio.sleep(60)